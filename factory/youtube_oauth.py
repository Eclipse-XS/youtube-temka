"""One-time host-side YouTube consent; no upload or publication is performed."""
import argparse
import json
import os
from pathlib import Path
import secrets
import httpx
from .legacy_drive_oauth import OAuthClient, DriveError, receive_code

SCOPES='https://www.googleapis.com/auth/youtube.upload https://www.googleapis.com/auth/youtube.readonly'
ANALYTICS_SCOPES='https://www.googleapis.com/auth/youtube.readonly https://www.googleapis.com/auth/yt-analytics.readonly'


def authorize(client_file, destination, *, analytics=False, open_browser=False):
    destination=Path(destination)
    if destination.exists():raise DriveError('youtube_token_already_exists_choose_another_alias')
    original=OAuthClient.read(Path(client_file))
    scopes=ANALYTICS_SCOPES if analytics else SCOPES
    client=OAuthClient(original.client_id,original.client_secret,scopes)
    verifier=secrets.token_urlsafe(64)
    code,redirect=receive_code(client,verifier,open_browser=True) if open_browser else receive_code(client,verifier)
    with httpx.Client(timeout=30,trust_env=False) as http:
        token=client.exchange(http,{'grant_type':'authorization_code','code':code,'redirect_uri':redirect,'code_verifier':verifier})
    if not isinstance(token.get('refresh_token'),str) or not token['refresh_token']:
        raise DriveError('oauth_refresh_token_missing')
    destination.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
    # Exclusive creation preserves a credential written concurrently by another operator.
    fd=os.open(destination,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    try:
        with os.fdopen(fd,'w',encoding='utf-8') as output:
            json.dump({'type':'authorized_user','client_id':client.client_id,'client_secret':client.client_secret,'refresh_token':token['refresh_token'],'scopes':scopes.split()},output)
    except Exception:
        destination.unlink(missing_ok=True)
        raise


def main():
    parser=argparse.ArgumentParser(description='Authorize a YouTube channel without uploading. Run on the host, then Discover in Publisher.')
    parser.add_argument('--client',required=True,type=Path,help='Existing Google desktop OAuth client JSON')
    parser.add_argument('--output',required=True,type=Path,help='New secrets/youtube/<alias>.json; existing files are never overwritten')
    parser.add_argument('--analytics',action='store_true',help='Separate read-only Analytics consent; save in secrets/analytics/<alias>.json')
    parser.add_argument('--open-browser',action='store_true',help='Open the system browser without printing the authorization URL')
    args=parser.parse_args()
    try:authorize(args.client,args.output,analytics=args.analytics,open_browser=args.open_browser)
    except (DriveError,OSError) as error:
        raise SystemExit(error.code if isinstance(error,DriveError) else 'youtube_authorization_storage_failed') from None
    print('YouTube authorization saved. Use Publisher Discover to verify the intended channel. Nothing was uploaded.')


if __name__=='__main__':main()
