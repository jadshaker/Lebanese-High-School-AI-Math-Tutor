import os, json

directory = "..\\json"
statistics = {}
total_exercises = 0
total_figure_given = 0

for filename in os.listdir(directory):
    with open(f"{directory}\\{filename}", "r") as file:
        print(f"[*] Collecting data from {filename}")

        data = json.load(file)
        num_exercises = len(data)
        figure_given = 0
        for exercise in data:
            if exercise["given_is_figure"]:
                figure_given += 1
        
        statistics[data[0]["chapter_title"]] = {
            "number_of_exercises": num_exercises,
            "figure_given": figure_given
        }

        total_exercises += num_exercises
        total_figure_given += figure_given

with open("exercise_statistics.txt", "w") as file:
    for chapter, stats in statistics.items():
        file.write(f"Chapter: {chapter}\n")
        file.write(f"  Number of Exercises: {stats['number_of_exercises']}\n")
        file.write(f"  Exercises with Given Figure: {stats['figure_given']}\n")
        file.write(f"  Percentage of Exercises with Given Figure: {stats['figure_given'] / stats['number_of_exercises'] * 100:.2f}%\n")
        file.write("=" * 40)
        file.write("\n")
    file.write(f"Total Number of Exercises: {total_exercises}\n")
    file.write(f"Total Exercises with Given Figure: {total_figure_given}\n")
    file.write(f"Total Percentage of Exercises with Given Figure: {total_figure_given / total_exercises * 100:.2f}%\n")

