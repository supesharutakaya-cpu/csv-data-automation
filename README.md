[日本語 / Japanese](README_ja.md)

# Local CSV Validator

[![Tests](https://github.com/supesharutakaya-cpu/csv-data-automation/actions/workflows/tests.yml/badge.svg)](https://github.com/supesharutakaya-cpu/csv-data-automation/actions/workflows/tests.yml)

Validate business CSV files on a Windows PC, normalize common formatting issues, and separate usable records from rows that need attention.

**Local-only processing. No CSV data is sent to external AI, APIs, or web services. The input file is never overwritten, moved, or deleted by the tool.**

| At a glance | |
| --- | --- |
| Validation | Required fields, duplicate IDs, email format, calendar dates, and numeric amounts |
| Results | `valid.csv` and `errors.csv`, with multiple error reasons per row |
| Safety | Read-only input access, output backups, recovery on ordinary write failures, and logs without sensitive row values |
| Quality | **82 automated tests passing**, including CLI, failure recovery, and input preservation checks |
| Runtime | Windows · Python 3.12+ · Standard library only; no runtime packages required |

Validation rules are separate from file handling, making the business logic straightforward to review and test. Documentation is available in English and Japanese. **CLI messages, log messages, and error reasons are currently in Japanese.** This documentation does not change the application's behavior.

## Quick start

### 1. Open the project in PowerShell

Download and extract the repository, then open the folder containing `README.md` and `run.py`. In File Explorer, type `powershell` into the address bar and press Enter.

Run the commands below from that project folder. Administrator privileges are not required.

### 2. Prepare a virtual environment

Install Python 3.12 or later if it is not already available. Create a project-local environment **only if `.venv` does not exist**:

```powershell
py -3 -m venv .venv
```

If the environment already exists, keep it and check its version:

```powershell
& '.\.venv\Scripts\python.exe' --version
```

There is no need to activate the environment, run `Activate.ps1`, change PowerShell's ExecutionPolicy, or install packages globally. Validation itself needs no additional packages.

### 3. Copy the public sample without overwriting existing input

Use a fresh copy of the project for this walkthrough. The following command stops if `data/input.csv` already exists. If it does, extract the project into a separate folder instead of replacing your data.

```powershell
if (Test-Path -LiteralPath '.\data\input.csv') {
    throw 'Input already exists. Use a fresh copy of the project instead of overwriting it.'
} else {
    New-Item -ItemType Directory -Path '.\data' -Force | Out-Null
    $samplePath = Join-Path (Get-Location) 'samples/public/example.csv'
    $inputPath = Join-Path (Get-Location) 'data/input.csv'
    [System.IO.File]::Copy($samplePath, $inputPath, $false)
}
```

The final `$false` disables overwriting, including if a destination file appears after the initial check. **Continue only if the copy succeeds.** The public sample remains unchanged.

### 4. Run validation

```powershell
& '.\.venv\Scripts\python.exe' -B '.\run.py'
```

The sample produces this console summary:

```text
総件数: 10
正常件数: 3
エラー件数: 7
重複件数: 2
```

These labels mean **10 total rows, 3 valid rows, 7 error rows, and 2 rows with duplicate IDs**. Output and log paths are also printed.

Enter `$LASTEXITCODE` immediately afterward to inspect the exit code. The sample returns **1** because it deliberately includes invalid rows; processing and output generation have completed successfully.

### 5. Use your own CSV

Prepare `data/input.csv` according to the schema below, following your own data-retention rules. The application reads that file without changing it.

UTF-8, with or without a BOM, is the default input encoding. For Windows CP932 input, use:

```powershell
& '.\.venv\Scripts\python.exe' -B '.\run.py' --encoding cp932
```

Encoding is selected explicitly, not guessed. Input and output paths are relative to the project containing `run.py`, regardless of the shell's current directory.

To see the available option:

```powershell
& '.\.venv\Scripts\python.exe' -B '.\run.py' --help
```

## Public sample data

[samples/public/example.csv](samples/public/example.csv) contains **entirely fictional data**. Names are artificial record labels, and email values use the example domain `example.com` or deliberately invalid strings. No real people or companies are represented.

| Sample ID | Demonstrates |
| --- | --- |
| `S001` | Trimming whitespace and normalizing a slash-separated date |
| `S002` | Normalizing an eight-digit date and accepting a zero amount |
| `S003` | Accepting a valid leap day and a negative decimal amount |
| `D001`, two rows | Flagging every occurrence of a duplicate ID |
| `E001` | A missing required name |
| `E002` | An invalid email format |
| `E003` | A date that does not exist |
| `E004` | A nonnumeric amount |
| `E005` | Reporting several problems in one row |

The sample's CLI behavior and documented counts are covered by an automated test in an isolated temporary project.

## Input schema and validation rules

Use a comma-separated CSV with a header row. **All six fields below are required.** Column names are case-sensitive; column order can vary.

```csv
id,name,email,date,amount,category
```

| Field | Rules |
| --- | --- |
| `id` | Nonblank text. Leading zeros are preserved; comparison is case-sensitive. |
| `name` | Nonblank text. Content is preserved apart from leading and trailing whitespace. |
| `email` | A common ASCII email format, such as `test@example.com`. |
| `date` | A real calendar date in year-first form: `2026-09-13`, `2026-9-3`, `2026/9/3`, or `20260903`. |
| `amount` | An ASCII integer or decimal, optionally signed: `100`, `-12.50`, `+5`, or `.5`. |
| `category` | Nonblank text. There is no fixed category allowlist. |

**Trimming and preservation**

Leading and trailing whitespace is removed from every field, including spaces, tabs, line breaks, and full-width spaces. Header names are trimmed too. Additional columns are retained and trimmed. Values inside a field are otherwise preserved, except for date normalization.

**Duplicate IDs**

Duplicates are detected after trimming. Every row sharing an ID is an error, **including the first occurrence**. Three rows with the same ID count as three duplicate rows. Blank IDs are required-field errors and do not contribute to the duplicate count.

**Dates and amounts**

Valid dates are normalized to `YYYY-MM-DD`, with leap-year validation. Ambiguous month-first or day-first formats, timestamps, times, and Japanese era dates are not supported.

Amounts cannot contain thousands separators, currency symbols, exponent notation, full-width digits, underscores, `NaN`, infinity, or a trailing decimal point without digits. Negative values are allowed. Amounts are validated without rounding or reformatting, so a value such as `001.2300` keeps its precision and representation.

**Email scope**

Email validation checks syntax only; it performs no DNS lookup, delivery check, or email sending. Internationalized addresses, quoted local parts, and domains without a dot are outside the supported format.

**CSV structure**

- Entirely blank lines are skipped. A record such as `,,,,,` is one invalid row.
- Quote fields containing commas or line breaks with double quotes. Escape a double quote inside a field by doubling it.
- Empty or duplicate header names are rejected.
- `error_reason` is reserved for output and cannot appear in the input header.
- Missing required columns, inconsistent field counts, or malformed CSV stop the entire run rather than silently discarding data.
- A file containing only the required header is valid and produces zero data rows. An empty file, or a BOM-only file, is a processing error.

## Output and error reporting

| Path | Contents |
| --- | --- |
| `output/valid.csv` | Rows that pass every check, retaining the input column order |
| `output/errors.csv` | Invalid rows, with an appended `error_reason` column |
| `logs/validation_<run-id>.log` | A separate processing log for each run |
| `output/.runs/<run-id>/` | Previous-output backups and, after a failure, staging files |

Both output CSVs use **UTF-8 with a BOM and CRLF line endings**. Each group retains its input row order. Headers are written even when a group has no data rows.

Error rows receive the same whitespace trimming and, where possible, date normalization. Invalid values remain available for inspection. Multiple reasons are joined with ` | ` in `error_reason`, for example:

```text
email: メールアドレスの形式が不正 | date: 日付の形式または日付が不正
```

This reports an invalid email format and an invalid date on the same row. The original input is preserved.

Logs and console messages report counts, timestamps, and diagnostic messages **without printing sensitive CSV row values**. Log filenames use UTC timestamps; timestamps inside logs use the PC's local time.

### Exit codes and troubleshooting

| Code | Meaning |
| --- | --- |
| `0` | Processing completed with no invalid rows, including a header-only input |
| `1` | Processing completed with invalid rows; inspect `errors.csv` |
| `2` | Processing stopped, or command-line arguments were invalid |

For a file or encoding error, check that the input exists, the selected encoding is correct, the project folder is writable, and sufficient disk space is available. Close output CSVs in Excel or other applications before retrying.

A structural input error leaves previous output files in place. If the log directory cannot be written, or a concurrent run is rejected, the application may report the problem only in the console.

## Safety and privacy

- **Local-only processing:** the application has no networking, external AI/API integration, or external-command execution feature.
- **Input preservation:** the input is opened read-only and is never overwritten, moved, or deleted by the tool.
- **Scoped writes:** application output is limited to the project's `output/` and `logs/` folders. Linked input/output paths, including symbolic links, junctions, and hard-linked files, are rejected.
- **Backup and recovery:** both new outputs are staged first. Existing outputs are copied to `output/.runs/<run-id>/*.previous` before replacement. If an ordinary replacement operation fails, the application attempts to restore any output it already replaced.
- **Controlled cleanup:** deletion is limited to the lock created by the run and a newly created output that must be removed during rollback. There is no bulk deletion of input files or folders.
- **Concurrent-run protection:** a lock prevents two instances from processing the same project at once.

After a forced termination, `logs/.csv-validator.lock` may remain. Confirm that no other instance is running, then rename **only that lock file** in File Explorer before retrying.

If recovery itself fails, or power is lost during output replacement, inspect the matching `*.previous` backups. Resolve the stale lock before rerunning, or restore the outputs manually. Updating the two output files is **not a crash-safe, all-or-nothing transaction**.

Outputs and backups still contain input-derived data. The tool does not anonymize or encrypt them; apply your organization's access and retention policies.

### Keep real data out of GitHub

`data/input.csv` is intentionally excluded from Git because it may contain customer or operational data. The `data/`, `output/`, and `logs/` directories are ignored except for their `.gitkeep` placeholders. CSV files are excluded by default wherever they are stored.

The only public CSV exception is `samples/public/example.csv`. Add further exceptions individually, and only after checking that each file is entirely fictional. The virtual environment, temporary files, logs, backups, and common secret-file formats are also excluded. `.env.example` may be tracked, but must contain example values only.

**Do not commit real data, generated outputs, logs, backups, or credentials.** Avoid force-adding ignored files. Ignore rules do not remove files that are already tracked, so review the files and contents selected for publication.

### Opening CSVs in Excel

Double-clicking a CSV may strip leading zeros or interpret values beginning with `=`, `+`, `-`, or `@` as formulas or other special values. This tool preserves data values and **does not neutralize spreadsheet formulas**.

For untrusted data, use Excel's **Data → From Text/CSV** import flow and set the columns to **Text** instead of opening the file directly.

## Continuous integration

The [Tests workflow](.github/workflows/tests.yml) runs the automated pytest suite on `windows-latest` with **Python 3.12 and 3.13** for pushes and pull requests. A failed test fails the corresponding job and the workflow.

CI uses fictional test fixtures and the public sample only. It does not use customer CSVs or configured secrets, and it does not upload artifacts. Repository permissions are limited to `contents: read`; checkout credentials are not persisted. Each job installs the test dependencies from `requirements.txt` in a virtual environment.

The badge above links to the workflow's live GitHub results. The existing **82 tests passing** result was verified locally; the first GitHub CI result becomes available after this workflow is pushed and runs. GitHub-hosted CI downloads its tools and dependencies, while the CSV validation application itself remains local-only.

## Environment and tests

Supported target: **Windows 10 or 11 with Python 3.12+**. Python 3.12 is the minimum because the path-safety checks use `Path.is_junction()`. Verification has been performed on Windows with **Python 3.13.15 and pytest 8.4.2**; this is not a claim of testing every Windows/Python combination.

The application uses only the Python standard library. `requirements.txt` pins pytest for testing.

If test dependencies have not been installed, run the following from the project root. Environment variables here affect only the current PowerShell process; they do not change OS settings. Temporary installation files stay inside the project, and pip caching is disabled.

```powershell
New-Item -ItemType Directory -Path '.tmp' -Force | Out-Null
$env:TEMP = Join-Path (Get-Location) '.tmp'
$env:TMP = $env:TEMP
$env:PYTHONDONTWRITEBYTECODE = '1'
& '.\.venv\Scripts\python.exe' -m pip --isolated install --no-cache-dir --disable-pip-version-check -r requirements.txt
```

Installing pytest initially requires access to a package distribution service. That installation does not read or send CSV data. Once dependencies are available, validation and tests can run offline.

Run all tests:

```powershell
& '.\.venv\Scripts\python.exe' -B -m pytest -q -p no:cacheprovider
```

**Verified result: 82 tests passing, with no failures or skips.**

Coverage includes valid data, every required field, duplicate IDs, invalid emails/dates/amounts, empty files, missing columns, multiple error reasons, encodings, extra columns, quoting, input preservation, output backups, recovery on write failure, private logging, concurrency, path checks, and CLI behavior.

Tests use fictional data in a fresh `.test-tmp/<random-id>/` directory and do not modify the existing input, outputs, or logs. The test configuration overrides `--basetemp` with a fresh project-local path to avoid deleting an existing test directory. See [REVIEW.md](REVIEW.md) for the detailed review record, currently in Japanese.

## Project structure

```text
csv-data-automation/
├── .github/workflows/tests.yml # Windows / Python 3.12 and 3.13 CI
├── README.md                   # English documentation
├── README_ja.md                # Japanese documentation
├── REVIEW.md                   # Verification record (Japanese)
├── run.py                      # Entry point
├── src/csv_validator/
│   ├── __init__.py
│   ├── __main__.py             # CLI arguments and exit codes
│   ├── validation.py           # Validation and normalization rules
│   └── application.py          # CSV I/O, logging, and recovery
├── tests/
│   ├── conftest.py             # Project-local temporary directories
│   ├── test_validation.py
│   ├── test_application.py
│   └── test_public_sample.py   # Public sample CLI verification
├── samples/public/example.csv # Fictional, publishable sample
├── data/input.csv              # Local input; excluded from Git
├── output/                     # Results and backups; excluded from Git
├── logs/                       # Logs; excluded from Git
├── .venv/                      # Project-local Python environment
├── .test-tmp/                  # Isolated test artifacts
├── .tmp/                       # Installation temporary files
├── pytest.ini
├── requirements.txt
└── .gitignore
```

The `.gitkeep` files preserve empty `data/`, `output/`, and `logs/` directories in Git. The local input is created by the user or the sample-copy step.

## Known limitations and future improvements

- All rows are loaded into memory. Very large CSV files have not been performance-tested.
- The per-field size limit is the Python CSV parser's default, normally 131,072 characters.
- Validation rules are fixed. Configurable schemas, category dictionaries, and business-specific amount ranges are not implemented.
- The two output replacements are not one atomic transaction. Forced termination or power loss can leave outputs from different runs.
- Path checks are not a security sandbox against a malicious process changing paths during a run. Use a trusted local project directory.
- There is no email-deliverability check, spreadsheet-formula neutralization, anonymization, or encryption.
- CLI messages, logs, and error reasons remain in Japanese.
- Logs, backups, and test artifacts accumulate without automatic cleanup. Review and remove unneeded artifacts manually according to your retention policy.

Potential next steps include Windows/Python CI coverage, configurable business rules, large-file processing, an optional Excel-safe export mode, and a short walkthrough using fictional data. Choose an appropriate license before distributing the project for reuse.
