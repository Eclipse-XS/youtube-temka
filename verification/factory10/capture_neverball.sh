#!/bin/sh
set -eu
sed -i 's@http://deb.debian.org@https://deb.debian.org@g' /etc/apt/sources.list.d/debian.sources
apt-get -o Acquire::Retries=1 -o Acquire::https::Timeout=20 update -qq
apt-get -o Acquire::Retries=1 -o Acquire::https::Timeout=20 install -y -qq --no-install-recommends neverball xvfb xdotool libgl1-mesa-dri >/tmp/game-install.log
export DISPLAY=:88 LIBGL_ALWAYS_SOFTWARE=1 SDL_AUDIODRIVER=dummy
mkdir -p /root/.neverball
printf 'width 640\nheight 480\nfullscreen 0\n' >/root/.neverball/neverballrc
Xvfb "$DISPLAY" -screen 0 640x480x24 -nolisten tcp >/tmp/xvfb.log 2>&1 &
sleep 1
data=/usr/share/games/neverball
find "$data" -name '*.sol' | sort >/tmp/game-maps.txt
sed -n '1,10p' /tmp/game-maps.txt
levels=$(grep '/map-easy/' /tmp/game-maps.txt | sed -n '2p;4p')
if [ -z "$levels" ]; then levels=$(sed -n '4p;6p' /tmp/game-maps.txt); fi
shot=0
for level in $levels; do
    shot=$((shot + 1))
    relative=${level#"$data/"}
    /usr/games/neverball "$relative" >/tmp/neverball.log 2>&1 &
    game=$!
    sleep 2
    xdotool search --onlyvisible --name '.*' getwindowname %@ || true
    window=$(xdotool search --onlyvisible --name '.*' | tail -1)
    if [ -n "$window" ]; then xdotool windowfocus "$window" || true; fi
    ffmpeg -nostdin -hide_banner -loglevel error -y -f x11grab -draw_mouse 0 -video_size 640x480 -framerate 24 \
        -i "$DISPLAY.0" -t 25 -c:v libx264 -preset ultrafast -threads 2 -pix_fmt yuv420p "/capture/neverball-$shot.mp4" &
    capture=$!
    sleep 1
    xdotool key Return
    sleep 2
    xdotool keydown Up
    sleep 3
    xdotool keyup Up keydown Right
    sleep 2
    xdotool keyup Right keydown Up
    sleep 3
    xdotool keyup Up
    sleep 1
    xdotool key Return
    sleep 2
    xdotool keydown Left
    sleep 2
    xdotool keyup Left keydown Up
    sleep 2
    xdotool keyup Up
    wait "$capture"
    kill -KILL "$game" 2>/dev/null || true
    wait "$game" 2>/dev/null || true
done
ls -l /capture/neverball-*.mp4
