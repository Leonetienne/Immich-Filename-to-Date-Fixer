# Immich date fixer
## Motivation
It turns out that a surprising number of perfectly ordinary things, uploading photos to a file server, downloading them again, sending them over Discord, breathing near them wrong, will happily strip or overwrite the creation date metadata. The images arrive in Immich with a timestamp of "right now" instead of when the photo was actually taken, which means your entire 2023 summer holiday ends up on whatever Tuesday you decided to sort your files.
This is particularly frustrating since this clutters the timeline AND the correct information is CLEARLY still at hand!
Look at the original filenames!
```
IMG_20230513_180448_217.jpg
IMG_20230502_222544_855.jpg
IMG_20230526_010448_714.jpg
IMG_20230526_010459_882.jpg
IMG_20230526_010433_786.jpg
IMG_20230526_010430_114.jpg
```
They clearly store the correct creation date.

```text
# This file
IMG_20230312_130300_383.jpg

# should be dated to
2023-03-12 13:03:00
```
So here this little tool exists to overwrite the media timeline date with the date parsed from their original filenames. I vibecoded it for myself but as others surely are having this problem too, I decided to share it.
Use it at your own risk and definitely back up your database first.

## How to run
The script runs in dry-run mode by default. It prints what it would change, but does not modify Immich unless you pass: `--apply`.  

### Prerequisites
You must be able to:
1. Reach your immich instance
2. Access the immich API (you must have an API key)
3. Identify the (wrong) day or a date range the media are mistakenly clustered to.

### Getting to it
Create a python venv or install `requests` directly.  
Creating a venv:
```bash
# You may skip this if you are using global installs with python
python3 -m venv venv
source ./venv/bin/activate
```

Installing requests:
```bash
# Definitely have to run this
python -m pip install -r requirements.txt
```


Set your Immich API key:
```bash
export IMMICH_API_KEY="your-api-key"
```

#### Basic usage
Dry-run:
```bash
python fix.py \
--url "https://your-immich.example.com" \
--bad-date "2025-04-15" \
--tz-offset "+02:00"
```

You can also use dry run with a date range to produce a CSV you can inspect to find even more wrongly assigned date clusters by looking for groups of `WOULD_CORRECT`:
```bash
python fix.py \
--url "https://your-immich.example.com" \
--bad-date-from '2025-01-11' \
--bad-date-to '2025-12-31' \
--tz-offset "+02:00"
```

![image](https://raw.githubusercontent.com/Leonetienne/Immich-Filename-to-Date-Fixer/refs/heads/master/github-assets/csv.png)

If you're feeling lucky, just run the date range with `--apply`.

Apply changes:
```bash
python fix.py \
  --url "https://your-immich.example.com" \
  --bad-date "2025-04-15" \
  --tz-offset "+02:00" \
  --apply
```

#### Also fixing the time-of-day (`--fix-time`)

If your filenames include a time component (e.g. `20260605_123049.jpg`) and you want the time corrected too — not just the date — pass `--fix-time`:

```bash
python fix.py \
  --url "https://your-immich.example.com" \
  --bad-date "2025-04-15" \
  --tz-offset "+02:00" \
  --fix-time \
  --apply
```

Whenever a date correction is applied (with or without `--fix-time`), the full datetime from the filename — including hours, minutes, and seconds — is written to Immich. `--fix-time` only affects the **"already correct" check**: without it, an asset whose date is already right is left untouched even if its time is wrong; with it, the time is compared too and corrected if it differs.

`--fix-time` has no effect on date-only filenames (those without an `HHMMSS` component); those always fall back to `12:00:00`.

### Output

The script prints lines like:
```text
File IMG_20230312_130300_383.jpg was corrected from 2025-04-15T10:00:00Z to 2023-03-12T12:03:00Z
```

Or:
```text
File IMG_20230312_130300_383.jpg was already on correct date 2023-03-12T12:03:00Z
```

By default, comparison is day-only — time of day is ignored when deciding whether a file is already correct. Use `--fix-time` to also correct the time-of-day when the filename contains it (see below).

### CSV report
This script generates a csv reporting what was done.

```text
immich-date-fix-2025-04-15.csv
```

You can override it the file name:
```bash
python fix.py \
  --url "https://your-immich.example.com" \
  --bad-date "2025-04-15" \
  --csv "my-report.csv"
```

### Supported filenames

The script looks for dates embedded in filenames.

It first looks for a full date and time in this form:

```text
YYYYMMDD_HHMMSS
```

or:

```text
YYYYMMDD-HHMMSS
```

Examples:

```text
IMG_20230312_130300_383.jpg
IMG-20230312-130300.jpg
20260605_123049.jpg
```

All parsed as their respective datetime, e.g.:

```text
2023-03-12 13:03:00
2026-06-05 12:30:49
```

If no time is found, the script looks for a date in this form:

```text
YYYYMMDD
```

Example:

```text
IMG-20230312-WA0042.jpg
```

This is parsed as:

```text
2023-03-12 12:00:00
```

Date-only filenames use `12:00:00` as the fallback time.

Invalid dates are skipped. For example:

```text
PXL_20232312.jpg
```

is skipped because `23` is not a valid month.

The script uses the first valid date pattern it finds in the filename.

