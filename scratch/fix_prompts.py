import glob

prompt_files = glob.glob('signals/gemini_prompt_p3_batch_*.txt')
old_text = """"Livestock Guardian Dogs" (LGDs) are dogs used by farmers to protect livestock from predators. Related terms include:
- **Livestock Guardian Dog** / **Guardian Dog** / **LGD**
- **Working Dog** / **Farm Dog**
- **Herding Dog**"""

new_text = """"Livestock Guardian Dogs" (LGDs) are dogs used by farmers to protect livestock from predators. Related terms include:
- **Livestock Guardian Dog** / **Guardian Dog** / **LGD**
- **Working Dog** / **Farm Dog** (MUST be specific to agriculture/farming, NOT just police dogs or guard breeds like Boxers/Mastiffs)
- **Herding Dog**"""

for file in prompt_files:
    with open(file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    if old_text in content:
        content = content.replace(old_text, new_text)
        with open(file, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"Updated {file}")
    else:
        print(f"Text not found in {file}")
