# Turbo Stage

[![Unit Tests](https://github.com/jberclaz/turbostage/actions/workflows/unit_tests.yml/badge.svg)](https://github.com/jberclaz/turbostage/actions/workflows/unit_tests.yml)
![Release](https://img.shields.io/github/v/release/jberclaz/turbostage)

This repository builds a frontend for the great [Dosbox Staging](https://github.com/dosbox-staging/dosbox-staging) emulator. It is inspired by [fs-uae-launcher](https://github.com/FrodeSolheim/fs-uae-launcher).

Available for Linux and Windows.

![screenshot](doc/screenshot.png)

## Getting started

After launching Turbo Stage, go to _File/Settings_ and adjust the following options:
1. Select the DosBox Staging path, or click the Download button to automatically install it;
2. Select the Games Path, where Turbo Stage expects to find DOS games;
3. If you want MT-32 music, select the location of the MT-32 ROM files, or click the Download button to automatically install them.

Next, you can select _File/Update game database_. This will download
settings for a few games. This is quite limited for now, but more
default settings will be added in the future.

## Adding games

Games should be archived in a zip file and all games zip files should
be placed in the folder you selected in the Settings dialog box. After
you added a few games, you can try clicking on _File/Scan local
games_. If some of your games are recognized, they will be configured automatically.

The other games must be added manually, to do that, click on _File/Add
new game_ and follow the instructions in the dialog box.

## Running a game

To run a game, you can double click on it in the list of games on the
left panel. Alternatively, you can select a game and click on the
large button _Launch Game_ at the bottom of the window.

## Configuring a game

To run a game settings menu, right-click on a game on the left panel
and choose _Run Game Setup_. You'll be presented with a dialog box
asking you to pick the settings executable. This typically varies with
every game. Common names are `setup.exe`, `soundset.exe`,
`config.exe`, etc. Note that not every game has such an option, but
most have. In general, you can at least choose among a few sound cards
and input methods. After you've finished running the setting program,
the options you've selected will be memorized for the next time you
run the game.

## Adjusting the emulator options

For each game, there are a few options you can tune. Those are
accessible by selecting a game, and then clicking on the _Setup_ tab,
on the right panel. There you can change the game executable,
customize the emulator speed (auto is a good selection for most games)
and pass additional DosBox options to the emulator.
