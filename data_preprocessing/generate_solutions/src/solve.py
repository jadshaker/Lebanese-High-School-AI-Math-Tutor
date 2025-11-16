import os
import json
import argparse
from pathlib import Path
from openai import OpenAI
from dotenv import load_dotenv
import time

# Load environment variables
load_dotenv()

# Initialize OpenAI client
client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))


def get_exercise_count(current_num, next_num):
    """
    Calculate how many exercises are combined in a single entry.
    
    Args:
        current_num: Current exercise number (string)
        next_num: Next exercise number (string or None)
        
    Returns:
        int: Number of exercises in this entry
    """
    if next_num is None:
        return 1
    
    # Convert to integers
    try:
        if current_num.isdigit() and next_num.isdigit():
            current_int = int(current_num)
            next_int = int(next_num)
            gap = next_int - current_int
            return max(1, gap)  # If gap is 2, it means current entry has 1 exercise (normal)
        else:
            return 1
    except:
        return 1


def solve_exercise(exercise_data, num_exercises=1):
    """
    Send an exercise to ChatGPT and get the solution.
    
    Args:
        exercise_data (dict): Dictionary containing exercise information
        num_exercises (int): Number of exercises combined in this entry
        
    Returns:
        dict or list: Single solution dict or list of solution dicts if multiple exercises
    """
    # Build the prompt
    exercise_text = exercise_data['exercise']
    chapter_title = exercise_data['chapter_title']
    chapter_number = exercise_data['chapter_number']
    exercise_number = exercise_data['exercise_number']
    
    if num_exercises > 1:
        prompt = f"""You are a mathematics tutor helping Lebanese high school students.

Chapter: {chapter_number}. {chapter_title}
Exercise Numbers: {exercise_number} through {int(exercise_number) + num_exercises - 1}

IMPORTANT: This text contains {num_exercises} separate exercises that were combined. Please identify and solve each exercise separately.

Combined Exercises:
{exercise_text}

For each exercise, provide ONLY the final answer(s) for each part/question. Do NOT include step-by-step explanations or intermediate steps.

If an exercise has multiple parts (e.g., 1°, 2°, 3°), list the final answer for each part.

Use LaTeX notation for mathematical expressions (wrapped in $ for inline or $$ for display math).

Format your response as:

## Exercise {exercise_number}
[Final answer(s) only]

## Exercise {int(exercise_number) + 1}
[Final answer(s) only]

(and so on for all {num_exercises} exercises)
"""
    else:
        prompt = f"""You are a mathematics tutor helping Lebanese high school students.

Chapter: {chapter_number}. {chapter_title}
Exercise Number: {exercise_number}

Exercise:
{exercise_text}

Please provide ONLY the final answer(s) for this exercise. Do NOT include step-by-step explanations, working, or intermediate steps.

If the exercise has multiple parts (e.g., 1°, 2°, 3°), list the final answer for each part clearly.

Use LaTeX notation for mathematical expressions (wrapped in $ for inline or $$ for display math).

Format: Provide concise final answers only.
"""

    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "system",
                    "content": "You are an expert mathematics tutor specializing in Lebanese high school curriculum. You provide clear, detailed, step-by-step solutions."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            temperature=0.7,
            max_tokens=4000 if num_exercises > 1 else 2000
        )
        
        solution = response.choices[0].message.content
        
        # If multiple exercises, try to split the response
        if num_exercises > 1:
            return split_multi_exercise_solution(solution, exercise_data, num_exercises)
        
        return solution
        
    except Exception as e:
        print(f"  Error getting solution: {str(e)}")
        return None


def split_multi_exercise_solution(solution, original_exercise, num_exercises):
    """
    Split a multi-exercise solution into separate exercise dictionaries.
    
    Args:
        solution (str): Combined solution from ChatGPT
        original_exercise (dict): Original exercise data
        num_exercises (int): Number of exercises to split into
        
    Returns:
        list: List of exercise dictionaries with individual solutions
    """
    import re
    
    # Try to split by "## Exercise N" pattern
    pattern = r'##\s*Exercise\s+(\d+)(.*?)(?=##\s*Exercise\s+\d+|\Z)'
    matches = list(re.finditer(pattern, solution, re.DOTALL | re.IGNORECASE))
    
    if len(matches) >= num_exercises:
        # Successfully split into individual exercises
        result = []
        base_exercise_num = int(original_exercise['exercise_number'])
        
        for i, match in enumerate(matches[:num_exercises]):
            ex_num = base_exercise_num + i
            ex_solution = match.group(2).strip()
            
            exercise_copy = original_exercise.copy()
            exercise_copy['exercise_number'] = str(ex_num)
            exercise_copy['answer'] = ex_solution
            result.append(exercise_copy)
        
        return result
    else:
        # Couldn't split properly, return as single exercise with note
        print(f"    Warning: Could not split {num_exercises} exercises, keeping combined")
        return solution


def process_json_file(input_file, output_file, delay=1.0, max_exercises=None):
    """
    Process a JSON file containing exercises and generate solutions.
    
    Args:
        input_file (Path): Path to input JSON file with exercises
        output_file (Path): Path to output JSON file with solutions
        delay (float): Delay in seconds between API calls to avoid rate limits
        max_exercises (int): Maximum number of exercises to solve (None for all)
    """
    # Read the input JSON file
    with open(input_file, 'r', encoding='utf-8') as f:
        exercises = json.load(f)
    
    print(f"\nProcessing {input_file.name}...")
    print(f"Total exercises: {len(exercises)}")
    if max_exercises:
        print(f"Solving first {max_exercises} exercises only")
    
    # Process each exercise
    solved_exercises = []
    exercises_solved = 0
    
    for i, exercise in enumerate(exercises, 1):
        # Check if we've reached the limit
        if max_exercises and exercises_solved >= max_exercises:
            # Add remaining exercises without solutions
            exercise_copy = exercise.copy()
            exercise_copy['answer'] = ""
            solved_exercises.append(exercise_copy)
            continue
        
        # Skip exercises with figures
        if exercise.get('given_is_figure', False):
            print(f"  Skipping exercise {exercise['exercise_number']} ({i}/{len(exercises)}) - has figure")
            exercise_copy = exercise.copy()
            exercise_copy['answer'] = "[Skipped - contains figure]"
            solved_exercises.append(exercise_copy)
            continue
        
        current_num = exercise['exercise_number']
        next_num = exercises[i]['exercise_number'] if i < len(exercises) else None
        
        # Determine if multiple exercises are combined
        num_exercises = get_exercise_count(current_num, next_num)
        
        if num_exercises > 1:
            end_num = int(current_num) + num_exercises - 1
            print(f"  Solving exercises {current_num}-{end_num} ({i}/{len(exercises)})...", end=' ')
        else:
            print(f"  Solving exercise {current_num} ({i}/{len(exercises)})...", end=' ')
        
        # Get solution from ChatGPT
        solution = solve_exercise(exercise, num_exercises)
        
        if solution:
            # Check if we got multiple exercises back (list of dicts)
            if isinstance(solution, list):
                # Multiple exercises were split successfully
                for ex_dict in solution:
                    solved_exercises.append(ex_dict)
                exercises_solved += len(solution)
                print(f"✓ (split into {len(solution)})")
            else:
                # Single exercise or couldn't split
                exercise_with_solution = exercise.copy()
                exercise_with_solution['answer'] = solution
                solved_exercises.append(exercise_with_solution)
                exercises_solved += 1
                print("✓")
        else:
            # If solution failed, still include exercise but with empty answer
            exercise_with_solution = exercise.copy()
            exercise_with_solution['answer'] = ""
            solved_exercises.append(exercise_with_solution)
            print("✗")
        
        # Delay to avoid rate limits
        if i < len(exercises):
            time.sleep(delay)
    
    # Save to output file
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(solved_exercises, f, indent=2, ensure_ascii=False)
    
    print(f"  Saved {len(solved_exercises)} solved exercises to {output_file.name}")
    return len(solved_exercises)


def process_all_json_files(input_dir, output_dir, delay=1.0, max_exercises=None):
    """
    Process all JSON files in the input directory.
    
    Args:
        input_dir (Path): Directory containing input JSON files
        output_dir (Path): Directory to save output JSON files
        delay (float): Delay in seconds between API calls
        max_exercises (int): Maximum number of exercises to solve per file (None for all)
    """
    input_dir = Path(input_dir)
    output_dir = Path(output_dir)
    
    if not input_dir.exists():
        print(f"Error: Input directory '{input_dir}' does not exist")
        return
    
    # Find all JSON files
    json_files = list(input_dir.glob('*.json'))
    
    if not json_files:
        print(f"No JSON files found in '{input_dir}'")
        return
    
    print(f"Found {len(json_files)} JSON file(s)")
    
    total_solved = 0
    for json_file in json_files:
        output_file = output_dir / json_file.name
        count = process_json_file(json_file, output_file, delay, max_exercises)
        total_solved += count
    
    print(f"\n{'='*50}")
    print(f"Total: {total_solved} exercises solved from {len(json_files)} file(s)")
    print(f"Output directory: {output_dir.absolute()}")


def main():
    parser = argparse.ArgumentParser(
        description='Generate solutions for exercises using ChatGPT',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Process all JSON files in a directory
  python solve.py --input ../../extract_exercises/src/json --output ./solutions
  
  # Process a specific JSON file
  python solve.py --input ../../extract_exercises/src/json/Trigonometric_lines.json --output ./solutions
  
  # Use custom delay between API calls (default is 1 second)
  python solve.py --input ../../extract_exercises/src/json --output ./solutions --delay 2.0
  
  # Solve only the first 5 exercises (skips exercises with figures)
  python solve.py --input ../../extract_exercises/src/json --output ./solutions --max 5
  
  # Combine options: solve first 10 exercises with 2-second delay
  python solve.py --input ../../extract_exercises/src/json --output ./solutions --max 10 --delay 2.0
        """
    )
    
    parser.add_argument(
        '--input', '-i',
        required=True,
        help='Input directory containing JSON files or path to a specific JSON file'
    )
    
    parser.add_argument(
        '--output', '-o',
        default='solutions',
        help='Output directory for JSON files with solutions (default: solutions)'
    )
    
    parser.add_argument(
        '--delay', '-d',
        type=float,
        default=1.0,
        help='Delay in seconds between API calls to avoid rate limits (default: 1.0)'
    )
    
    parser.add_argument(
        '--max', '-n',
        type=int,
        default=None,
        help='Maximum number of exercises to solve (default: all exercises). Exercises with figures are always skipped.'
    )
    
    args = parser.parse_args()
    
    # Check if OPENAI_API_KEY is set
    if not os.getenv('OPENAI_API_KEY'):
        print("Error: OPENAI_API_KEY environment variable is not set")
        print("Please set it in a .env file or export it in your environment")
        return
    
    input_path = Path(args.input)
    
    # Check if input is a file or directory
    if input_path.is_file() and input_path.suffix == '.json':
        # Process single JSON file
        output_file = Path(args.output) / input_path.name
        count = process_json_file(input_path, output_file, args.delay, args.max)
        print(f"\nSolved {count} exercises")
        print(f"Output file: {output_file.absolute()}")
    elif input_path.is_dir():
        # Process all JSON files in directory
        process_all_json_files(input_path, args.output, args.delay, args.max)
    else:
        print(f"Error: '{input_path}' is not a valid JSON file or directory")


if __name__ == '__main__':
    main()
