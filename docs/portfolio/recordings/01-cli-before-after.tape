Output docs/portfolio/recordings/01-terminal-proof.mp4

Set Shell "zsh"
Set FontSize 24
Set Width 1600
Set Height 900
Set Margin 32
Set MarginFill "#10100F"
Set Theme "Catppuccin Mocha"
Set TypingSpeed 35ms

Type "export PS1='reelcut > '; clear"
Enter
Sleep 1s

Type ".venv/bin/reelcut timeline assets/ht-ghd-better-gitcli/DF4506C5-2F13-40FB-AC7A-8EC4943DAB22.captions.json | head -24"
Enter
Sleep 5s

Type "clear; printf '%s\\n' 'REELCUT / EXISTING BEFORE + AFTER ARTIFACTS'"
Enter
Sleep 500ms

Type "ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1 assets/ht-ghd-better-gitcli/DF4506C5-2F13-40FB-AC7A-8EC4943DAB22.MOV"
Enter
Sleep 1s

Type "ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1 output/ht-ghd-better-gitcli/git-cli-isnt-a-personality.mp4"
Enter
Sleep 1s

Type "ls -1 output/ht-ghd-better-gitcli"
Enter
Sleep 2s
