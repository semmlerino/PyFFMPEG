ShotBot

VFX Shot Launcher — Project Brief 
I work in VFX on Linux workstations, running many common tools via the terminal. I want to build a PySide6 GUI wrapper to automate this, with visual shot selection and context-aware app launching.

The app will be called ShotBot

🎯 Goals
Build a PySide6 GUI that wraps frequently used commands.

Display shots (from Shotgun) visually in a thumbnail grid.

Allow launching apps in shot context, in the same terminal session.

Persist last selected shot across sessions.

Log all executed commands in the UI.

🛠️ Commands to Wrap
From any shot directory:

3de

nuke

maya

rv

publish_standalone

Global command (to fetch shot list):

ws -sg — returns scheduled shots, e.g.:

swift
Copy
Edit
workspace /shows/ygsk/shots/108_BQS/108_BQS_0005
🖼️ Shot Thumbnails
For each shot:

Thumbnail path pattern:

ruby
Copy
Edit
/shows/<show>/shots/<sequence>/<shot>/publish/editorial/cutref/v001/jpg/1920x1080/
Load any .jpg from this folder (first found).

If no JPG exists, show a placeholder.

Grid layout should support resizing thumbnails.

💡 Behavior
When a user clicks on a shot:

Show buttons for launching apps.

Running an app should:

cd into the shot directory.

Launch the app in the same terminal.

Display the command in a log view.

The app should remember the last selected shot between sessions (e.g., store in a config file or JSON).

🖥️ UI Features
Grid of shot cards: thumbnail + shot name.

Resizable thumbnails.

Launcher panel: buttons for each tool.

Log panel: rolling history of launched commands.

Persistent config:

Last selected shot

Optional future preferences