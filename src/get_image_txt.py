#!/usr/bin/python

import os
from typing import List, Dict, Union
from google.genai import Client, types


def get_image_exercise_text(image_path: str, image_description: str) -> Dict[str, str]:
    """
    Extract exercise text, description, math topics and YouTube keywords from image(s) using Google Gemini API.
    
    Args:
        image_paths: Single image path (str) or list of image paths
        api_key: Google Gemini API key. If not provided, will use GEMINI_API_KEY env variable.
    
    Returns:
        Dictionary with keys:
            - 'description': The full exercise text extracted from the image(s)
            - 'keywords': Comma-separated YouTube keywords for the exercise
    
    Raises:
        FileNotFoundError: If any image file doesn't exist
        ValueError: If API key is not provided and not found in environment
    """
    # Initialize Gemini client
    api_key = "AIzaSyBrzoLUiDA2ycGfJb2a2Vjp5KX1qxFLlVc"
    
    client = Client(api_key=api_key)
    
    # Normalize input to list
    if isinstance(image_path, str):
        image_path = [image_path]
    
    # Validate all files exist
    for path in image_path:
        if not os.path.exists(path):
            raise FileNotFoundError(f"Image file not found: {path}")
    
    # Read images as bytes and create Parts
    image_parts = []
    for path in image_path:
        with open(path, "rb") as image_file:
            image_data = image_file.read()
            # Determine MIME type from file extension
            ext = os.path.splitext(path)[1].lower()
            mime_type_map = {
                ".jpg": "image/jpeg",
                ".jpeg": "image/jpeg",
                ".png": "image/png",
                ".gif": "image/gif",
                ".webp": "image/webp"
            }
            mime_type = mime_type_map.get(ext, "image/jpeg")
            
            # Create Part from bytes
            image_part = types.Part.from_bytes(data=image_data, mime_type=mime_type)
            image_parts.append(image_part)
    
    # Prepare the prompt
    prompt = f"""Please analyze the image(s) and extract:
1. The complete exercise text (all questions, instructions, and content visible in the image). use only raw text without math latex.
2. A brief summary of what the exercise is about with math topics, names of the formulas used.
3. YouTube keywords (comma-separated, relevant for search)

{f"Image metadata: {image_description}" if image_description else ""}
All Text should be in Hebrew. No more than 4500 characters.

Format your response as:

[brief summary of the exercise]
--------------------------------
[full exercise text here]
--------------------------------
KEYWORDS:
[comma-separated keywords here]
"""
    
    # Prepare content with prompt and images
    content = [prompt] + image_parts
    
    # Send to Gemini API
    response = client.models.generate_content(
        model='gemini-2.5-flash',
        contents=content
    )
    
    # Get the response text
    response_text = response.text

    print(response.usage_metadata)

    # Parse the response to extract description and keywords
    description = ""
    keywords = ""
    
    # Split by the separators
    if "KEYWORDS:" in response_text:
        parts = response_text.split("KEYWORDS:")
        if len(parts) > 1:
            keywords = parts[1].strip()
            # Get description part (everything before KEYWORDS)
            desc_part = parts[0]
            if "--------------------------------" in desc_part:
                # Extract both summary and full exercise text
                desc_sections = desc_part.split("--------------------------------", 1)
                summary = desc_sections[0].strip()
                if len(desc_sections) > 1:
                    full_text = desc_sections[1].strip()
                    # Combine summary and full text
                    description = f"{summary}\n\n{full_text}"
                else:
                    description = summary
            else:
                description = desc_part.strip()
    elif "--------------------------------" in response_text:
        # If no KEYWORDS section, extract both summary and full text
        parts = response_text.split("--------------------------------", 1)
        summary = parts[0].strip()
        if len(parts) > 1:
            full_text = parts[1].strip()
            # Combine summary and full text
            description = f"{summary}\n\n{full_text}"
        else:
            description = summary
    else:
        description = response_text.strip()
    
    # Clean text
    description = description.replace("בסד", "").replace("""בס"ד""", "").replace("שאלון 806", "").replace("שאלון 807", "").replace("שאלון 803", "").replace("שאלון 804", "").replace("שאלון 805", "").strip()
    keywords = keywords.replace("בסד", "").replace("""בס"ד""", "").replace("שאלון 806", "").replace("שאלון 807", "").replace("שאלון 803", "").replace("שאלון 804", "").replace("שאלון 805", "").strip()
    
    return {
        "description": description,
        "keywords": keywords
    }


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Extract exercise text and summary from image(s)")
    parser.add_argument("--image", required=True, help="Path to image file (or comma-separated paths for multiple images)")
    parser.add_argument("--api-key", help="Gemini API key (or set GEMINI_API_KEY env variable)")
    args = parser.parse_args()
    
    # Parse image paths
    image_paths = [path.strip() for path in args.image.split(",")]
    
    try:
        result = get_image_exercise_text(image_paths)
        print("\n" + "="*50)
        print("DESCRIPTION:")
        print("="*50)
        print(result["description"])
        print("\n" + "="*50)
        print("KEYWORDS:")
        print("="*50)
        print(result["keywords"])
        print("\n" + "="*50)
    except Exception as e:
        print(f"Error: {e}")
        exit(1)
