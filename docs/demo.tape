# dsoxlab demo — regenerate with:  vhs docs/demo.tape   (from the repo root)
# Requires a sibling lab catalog checked out at ../linux-dsoxlab-training
Output docs/demo.gif

Set Shell "bash"
Set FontSize 15
Set Width 1320
Set Height 820
Set Padding 20
Set Theme "Catppuccin Mocha"

# Hidden setup: enter a lab catalog and use a clean prompt.
Hide
Type "cd ../linux-dsoxlab-training && export PS1='$ ' && clear"
Enter
Show

Sleep 600ms
Type "dsoxlab --version"
Enter
Sleep 1200ms

Type "# the catalog is detected automatically from the repo's meta.yml"
Enter
Type "dsoxlab list-labs --level l1"
Enter
Sleep 3500ms

Type "dsoxlab show l1-01-discover-linux-map"
Enter
Sleep 4s
