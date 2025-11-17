# Exercise Solution Generator

This tool uses OpenAI's ChatGPT to generate detailed step-by-step solutions for math exercises.

## Setup

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Create a `.env` file with your OpenAI API key:
```bash
cp .env.example .env
```

3. Edit `.env` and add your OpenAI API key:
```
OPENAI_API_KEY=sk-your-actual-api-key-here
```

## Usage

### Process all JSON files in a directory

```bash
python src/solve.py --input ../extract_exercises/src/json --output src/solutions
```

### Process a specific JSON file

```bash
python src/solve.py --input ../extract_exercises/src/json/Trigonometric_lines.json --output src/solutions
```

### Custom delay between API calls

To avoid rate limits, you can set a custom delay (in seconds) between API calls:

```bash
python src/solve.py --input ../extract_exercises/src/json --output src/solutions --delay 2.0
```

### Solve only first N exercises

To solve only a specific number of exercises (useful for testing):

```bash
python src/solve.py --input ../extract_exercises/src/json --output src/solutions --max 5
```

### Combine options

```bash
python src/solve.py --input ../extract_exercises/src/json --output src/solutions --max 10 --delay 2.0
```

## Command-line Arguments

- `--input` / `-i` (required): Input directory containing JSON files or path to a specific JSON file
- `--output` / `-o` (default: `solutions`): Output directory for JSON files with solutions
- `--delay` / `-d` (default: `1.0`): Delay in seconds between API calls to avoid rate limits
- `--max` / `-n` (optional): Maximum number of exercises to solve. Exercises with figures are automatically skipped

## Output Format

The output JSON files will have the same structure as the input files, with an additional `answer` field containing the solution for each exercise:

```json
{
  "chapter_title": "TRIGONOMETRIC LINES",
  "chapter_number": "11",
  "chapter_attribute": "trigonometry",
  "exercise_number": "1",
  "exercise": "...",
  "given_is_figure": false,
  "answer": "Detailed step-by-step solution..."
}
```

## Notes

- The script uses GPT-4o model by default
- Solutions are formatted with LaTeX notation for mathematical expressions
- A delay is added between API calls to respect rate limits
- If an API call fails, the exercise is still included with an empty answer field
- **Exercises with figures are automatically skipped** (marked with `[Skipped - contains figure]`)
- When multiple exercises are combined in one entry (detected by gaps in numbering), the script attempts to split them into separate solutions
