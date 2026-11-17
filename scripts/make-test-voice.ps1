param([string]$Output='verification/voice-friendly.wav')
$ErrorActionPreference='Stop'
Set-Location (Split-Path -Parent $PSScriptRoot)
Add-Type -AssemblyName System.Speech
$speaker=New-Object System.Speech.Synthesis.SpeechSynthesizer
try {
    $speaker.SelectVoice('Microsoft Zira Desktop')
    $speaker.Volume=95
    $speaker.SetOutputToWaveFile((Join-Path (Get-Location) $Output))
    $speaker.SpeakSsml(@'
<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xml:lang="en-US">
  <prosody rate="-5%">
    Hi there. <break time="180ms"/>
    Let's turn a long video into a clear, enjoyable short.
    <break time="220ms"/>
    Start with one simple idea. Give it a natural opening, keep the useful part,
    and let the ending feel complete.
    <break time="220ms"/>
    Clear speech and well timed captions make every moment easier to follow.
    <break time="200ms"/>
    This little example was created locally, just to check the editing workflow.
  </prosody>
</speak>
'@)
} finally {
    $speaker.Dispose()
}
