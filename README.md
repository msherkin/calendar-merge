# Calendar Merge

Combines groups of calendars into one subscribable calendar per group, for
example all appointments in one, all school calendars in another. Family
members subscribe once to each combined calendar on their phones. GitHub
re-downloads the source calendars every hour and republishes the combined
ones, for free.

## How the pieces fit

- **Lists of calendars.** Each group is a list of `Name | URL` lines. On the
  Mac they are files named `<group>_calendars.txt` (for example
  `appointment_calendars.txt`). These files are never uploaded: calendar
  links are private, and this repository is public. Instead, each list is
  pasted into a GitHub **secret** named `<GROUP>_CALENDARS`.
- **The merge.** [merge.py](merge.py) downloads every calendar in every list
  and writes one `<group>.ics` per list.
- **Publishing.** The [workflow](.github/workflows/merge.yml) runs the merge
  every hour and publishes the results with GitHub Pages, inside a folder
  whose random name is itself a secret (`PUBLISH_FOLDER`). The combined
  calendars can only be found by someone who has the link, the same way
  iCloud and Google "secret address" calendars work.

Settings you can put at the top of any list:

```
# title: Family Appointments     name shown on phones
# prefix: yes                    puts "[Name]" in front of each event title
# history days: 120              drops one-off events older than this
```

## Common tasks

**Add or remove a calendar in a group.** Edit the `.txt` file on the Mac,
then on GitHub go to Settings → Secrets and variables → Actions, click the
pencil next to that group's secret, paste the whole file in, and save. Then
Actions tab → Merge calendars → Run workflow (otherwise it updates within
the hour).

**Add a new group.** Make a new file such as `sports_calendars.txt`, add a
secret named `SPORTS_CALENDARS` with its contents, and run the workflow. It
appears as `sports.ics` next to the others. No code changes needed.

**Test on the Mac.** In Terminal, in this folder:

```
python3 merge.py
```

writes the combined calendars into an `output` folder.

## If something goes wrong

- If any calendar can't be downloaded, the run stops without publishing, so
  the last good version stays online and GitHub emails you about the failed
  run. The Actions log names the calendar that failed. A link that has
  stopped working needs replacing or removing from its secret.
- GitHub pauses hourly jobs in public repositories after 60 days without
  changes. The workflow tries to keep itself switched on; if GitHub ever
  emails that it was disabled, open the Actions tab and click Enable.
- Phones decide how often to re-download a subscribed calendar. On iPhone,
  pick the refresh interval when subscribing; Google Calendar refreshes
  every 12–24 hours on its own.
