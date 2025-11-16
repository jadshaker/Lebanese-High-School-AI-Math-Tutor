import re
import json
import zipfile
import argparse
from pathlib import Path
import sys


# Category mapping dictionary
CATEGORY_MAP = {
    "Arithmetic": [
        "Sets and cartesian product",
        "Absolute value and intervals",
        "Powers and radicals",
        "Order on R - Framing and approximation"
    ],
    "Algebra": [
        "The polynomials",
        "First degree equations and inequalities in one unknown",
        "Mapping - bijection",
        "Generalities about functions",
        "Equations of straight lines",
        "Linear systems",
        "Study of functions"
    ],
    "Geometry": [
        "Addition of vectors",
        "Multiplication of a vector by a real number",
        "Projection in the plane",
        "Coordinate system",
        "Cavalier perspective",
        "Straight lines and planes",
        "Parallel straight lines and planes"
    ],
    "Trigonometry": [
        "Trigonometric circle - Oriented arc",
        "Trigonometric lines"
    ],
    "Statistics": [
        "Statistics"
    ],
    "Probability / Counting": [
        "Counting"
    ]
}


def get_chapter_attribute(chapter_title):
    """Determine chapter attribute based on chapter title"""
    # Normalize the chapter title for comparison (lowercase, strip whitespace)
    normalized_title = chapter_title.strip().lower()
    
    # Check each category
    for category, titles in CATEGORY_MAP.items():
        for title in titles:
            if normalized_title in title.lower() or title.lower() in normalized_title:
                return category.lower()
    
    # Default to algebra if no match found
    return "algebra"


def roman_to_int(roman):
    """Convert Roman numeral to integer."""
    roman_map = {
        'I': 1, 'II': 2, 'III': 3, 'IV': 4, 'V': 5,
        'VI': 6, 'VII': 7, 'VIII': 8, 'IX': 9, 'X': 10
    }
    return roman_map.get(roman, None)


def extract_exercises_from_content(content, chapter_name):
    """Extract exercises from markdown content"""
    
    # Extract chapter number (first # heading with just a number)
    chapter_number_match = re.search(r'^# (\d+)\s*$', content, re.MULTILINE)
    chapter_number = chapter_number_match.group(1) if chapter_number_match else ""
    
    # Extract chapter title (second # heading, which should be the title)
    # Look for the heading after the number
    if chapter_number_match:
        # Find the next # heading after the chapter number
        remaining_content = content[chapter_number_match.end():]
        title_match = re.search(r'^# (.+?)\s*$', remaining_content, re.MULTILINE)
        chapter_title = title_match.group(1).strip() if title_match else chapter_name
    else:
        # Fallback: use the first # heading as title
        chapter_title_match = re.search(r'^# (.+)', content, re.MULTILINE)
        chapter_title = chapter_title_match.group(1).strip() if chapter_title_match else chapter_name
    
    # Determine chapter attribute based on title
    chapter_attribute = get_chapter_attribute(chapter_title)
    
    # Find the EXERCISES section
    exercises_section_match = re.search(
        r'# EXERCISES AND PROBLEMS\s*(.+?)(?=\Z)', 
        content, 
        re.DOTALL
    )
    
    if not exercises_section_match:
        return []
    
    exercises_content = exercises_section_match.group(1)
    
    # Remove section headers (like "Test your knowledge", "For seeking", "To go further")
    # Keep only content after these headers
    exercises_content = re.sub(r'^# [A-Z][a-z].*$', '', exercises_content, flags=re.MULTILINE)
    
    # Remove math blocks to avoid matching numbers inside them
    # Temporarily replace math blocks with placeholders
    math_blocks = []
    def save_math_block(match):
        math_blocks.append(match.group(0))
        return f'__MATHBLOCK_{len(math_blocks)-1}__'
    
    exercises_content = re.sub(r'\$\$.*?\$\$', save_math_block, exercises_content, flags=re.DOTALL)
    exercises_content = re.sub(r'\$.*?\$', save_math_block, exercises_content)
    
    # Split by exercise numbers - handle both regular numbers and Roman numerals
    # Pattern: number/Roman numeral at start of line, followed by space, then non-whitespace content
    # Lookahead to next exercise number or end of string
    exercise_pattern = r'^\n?(\d{1,2}|I{1,3}|IV|V|VI{0,3}|IX|X)\s+(\S.*?)(?=\n(?:\d{1,2}|I{1,3}|IV|V|VI{0,3}|IX|X)\s+\S|\Z)'
    
    exercises = []
    matches = list(re.finditer(exercise_pattern, exercises_content, re.MULTILINE | re.DOTALL))
    
    for i, match in enumerate(matches):
        exercise_num = match.group(1)
        exercise_content = match.group(2).strip()
        
        # Filter out false matches (content that is clearly not an exercise)
        # Skip if content is too short (less than 10 chars) or starts with math symbols only
        if len(exercise_content) < 10:
            continue
        
        # Skip if it looks like a formula continuation (starts with operators/symbols)
        if re.match(r'^[\+\-\=\*\/\(\)\[\]]+', exercise_content):
            continue
        
        # Restore math blocks
        for idx, math_block in enumerate(math_blocks):
            exercise_content = exercise_content.replace(f'__MATHBLOCK_{idx}__', math_block)
        
        # Check if there's a figure (image reference)
        has_figure = bool(re.search(r'!\[.*?\]\(.*?\)', exercise_content))
        
        # Convert Roman numerals to integers
        converted_num = roman_to_int(exercise_num)
        if converted_num is not None:
            exercise_num = str(converted_num)
        
        exercise_dict = {
            "chapter_title": chapter_title,
            "chapter_number": chapter_number,
            "chapter_attribute": chapter_attribute,
            "exercise_number": exercise_num,
            "exercise": exercise_content,
            "given_is_figure": has_figure
        }
        
        exercises.append(exercise_dict)
    
    return exercises


def process_zip_file(zip_path, output_dir):
    """Process a single zip file and extract exercises"""
    zip_path = Path(zip_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    chapter_name = zip_path.stem  # Get filename without extension
    
    print(f"Processing {zip_path.name}...")
    
    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
        # Get all .md files in the zip
        md_files = [f for f in zip_ref.namelist() if f.endswith('.md') and not f.startswith('__MACOSX')]
        
        if not md_files:
            print(f"  Warning: No .md files found in {zip_path.name}")
            return 0
        
        # Process the first .md file (or you can process all if needed)
        md_file = md_files[0]
        
        # Read the file content directly from zip
        with zip_ref.open(md_file) as f:
            content = f.read().decode('utf-8')
        
        # Extract exercises
        exercises = extract_exercises_from_content(content, chapter_name)
        
        if not exercises:
            print(f"  Warning: No exercises found in {zip_path.name}")
            return 0
        
        # Save to JSON file named after the chapter
        output_file = output_dir / f"{chapter_name}.json"
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(exercises, f, indent=2, ensure_ascii=False)
        
        print(f"  Extracted {len(exercises)} exercises -> {output_file.name}")
        return len(exercises)


def process_all_zips(input_dir, output_dir):
    """Process all zip files in the input directory"""
    input_dir = Path(input_dir)
    
    if not input_dir.exists():
        print(f"Error: Input directory '{input_dir}' does not exist")
        sys.exit(1)
    
    zip_files = list(input_dir.glob('*.zip'))
    
    if not zip_files:
        print(f"No zip files found in '{input_dir}'")
        sys.exit(1)
    
    print(f"Found {len(zip_files)} zip file(s)\n")
    
    total_exercises = 0
    for zip_file in zip_files:
        count = process_zip_file(zip_file, output_dir)
        total_exercises += count
    
    print(f"\n{'='*50}")
    print(f"Total: {total_exercises} exercises extracted from {len(zip_files)} file(s)")
    print(f"Output directory: {Path(output_dir).absolute()}")


def main():
    parser = argparse.ArgumentParser(
        description='Extract exercises from markdown files in zip archives',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Process all zip files in a directory
  python extract_exercises.py --input ./latex_output --output ./json
  
  # Process a specific zip file
  python extract_exercises.py --input ./latex_output/chapter1.zip --output ./json
  
  # Use default output directory (./json)
  python extract_exercises.py --input ./latex_output
        """
    )
    
    parser.add_argument(
        '--input', '-i',
        required=True,
        help='Input directory containing zip files or path to a specific zip file'
    )
    
    parser.add_argument(
        '--output', '-o',
        default='json',
        help='Output directory for JSON files (default: json)'
    )
    
    args = parser.parse_args()
    
    input_path = Path(args.input)
    
    # Check if input is a file or directory
    if input_path.is_file() and input_path.suffix == '.zip':
        # Process single zip file
        count = process_zip_file(input_path, args.output)
        print(f"\nExtracted {count} exercises")
        print(f"Output directory: {Path(args.output).absolute()}")
    elif input_path.is_dir():
        # Process all zip files in directory
        process_all_zips(input_path, args.output)
    else:
        print(f"Error: '{input_path}' is not a valid zip file or directory")
        sys.exit(1)


if __name__ == '__main__':
    main()
