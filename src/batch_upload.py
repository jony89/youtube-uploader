#!/usr/bin/python

import os
import sys
import time
import glob
import argparse
import csv
import re
from pathlib import Path

# Add parent directory to path to import upload_video module
sys.path.insert(0, os.path.dirname(__file__))

from upload_video import (
    get_authenticated_service,
    initialize_upload,
    VALID_PRIVACY_STATUSES,
)
from get_image_txt import get_image_exercise_text
import cv2
import tempfile

# Constants
INTERVAL_BETWEEN_UPLOADS = 30  # seconds between each upload
MP4_EXTENSION = "*.mp4"


def load_video_metadata(csv_path):
    """
    Load video metadata from CSV file.

    Args:
        csv_path (str): Path to the CSV file containing video metadata

    Returns:
        dict: Dictionary mapping filename to metadata (title, description, tags)
    """
    metadata = {}
    try:
        with open(csv_path, "r", encoding="utf-8") as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                description = row["description"]

                if description: 
                    description = description.replace("[B]", "")
                    description = description.replace("[/B]", "")


                filename = row["filename"]
                metadata[filename] = {
                    "title": row["title"]
                    .replace("שאלון 803 - ", "")
                    .replace("שאלון 804 - ", "")
                    .replace("שאלון 804, ", "")
                    .replace("שאלון 804 ו 803 - ", "")
                    .replace("שאלון 805 -", "")
                    .replace("שאלון 805 ושאלון 807 - ", "")
                    .replace("שאלון 807 ושאלון 805 - ", "")
                    .replace("שאלון 806 -", "")
                    .replace("שאלון 803, 804 ו 806 - ", "")
                    .replace("שאלון 807 -", "")
                    .replace("שאלון 803", "")
                    .strip(),
                    "description": description,
                    "tags": row["tags"],
                }
    except FileNotFoundError:
        print(f"Warning: CSV file not found at {csv_path}")
    except KeyError as e:
        print(f"Error: Missing expected column in CSV: {e}")

    return metadata


def get_mp4_files(folder_path):
    """
    Get all MP4 files from the specified folder.

    Args:
        folder_path (str): Path to the folder containing MP4 files

    Returns:
        list: Sorted list of MP4 file paths
    """
    if not os.path.isdir(folder_path):
        raise ValueError(f"Invalid folder path: {folder_path}")

    mp4_files = glob.glob(os.path.join(folder_path, MP4_EXTENSION))
    return sorted(mp4_files)


def clean_description_for_youtube(description):
    """
    Clean description to ensure it's valid for YouTube API.
    
    Args:
        description (str): Raw description text
    
    Returns:
        str: Cleaned description
    """
    if not description:
        return ""
    
    # Remove angle brackets (YouTube doesn't allow < and >)
    description = description.replace('<', '').replace('>', '')
    
    # Remove control characters except newlines and tabs
    # Remove null bytes and other problematic control characters
    description = description.replace('\x00', '')
    description = re.sub(r'[\x01-\x08\x0B\x0C\x0E-\x1F\x7F-\x9F]', '', description)
    
    # Remove any remaining problematic control characters
    # But keep all valid Unicode characters (Hebrew, math symbols, etc.)
    # Only remove actual control characters
    description = ''.join(char for char in description if ord(char) >= 32 or char in '\n\t\r')
    
    # Normalize multiple consecutive newlines to max 2
    description = re.sub(r'\n{3,}', '\n\n', description)
    
    # Check byte size (YouTube limit is 5000 bytes, not characters)
    # Hebrew characters use 2-3 bytes each in UTF-8
    description_bytes = description.encode('utf-8')
    if len(description_bytes) > 5000:
        # Truncate by bytes, not characters
        truncated_bytes = description_bytes[:4997]
        description = truncated_bytes.decode('utf-8', errors='ignore') + "..."
        print(f"  Warning: Description truncated to 5000 bytes (was {len(description_bytes)} bytes)")
    
    # Strip whitespace but preserve newlines
    description = description.strip()
    
    # Final validation - ensure it's not empty and is valid UTF-8
    try:
        description.encode('utf-8')
    except UnicodeEncodeError:
        # If encoding fails, use error handling
        description = description.encode('utf-8', errors='ignore').decode('utf-8', errors='ignore')
    
    return description


def extract_frame_from_video(video_path, frame_time=0):
    """
    Extract a frame from a video at the specified time.
    
    Args:
        video_path (str): Path to the video file
        frame_time (float): Time in seconds to extract frame (default: 0)
    
    Returns:
        str: Path to the extracted frame image file, or None if extraction failed
    """
    try:
        # Open video file
        cap = cv2.VideoCapture(video_path)
        
        if not cap.isOpened():
            print(f"  Warning: Could not open video file: {video_path}")
            return None
        
        # Get FPS to calculate frame number
        fps = cap.get(cv2.CAP_PROP_FPS)
        if fps == 0:
            fps = 30  # Default FPS if cannot be determined
        
        # Calculate frame number
        frame_number = int(frame_time * fps)
        
        # Set video position to the desired frame
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_number)
        
        # Read frame
        ret, frame = cap.read()
        cap.release()
        
        if not ret or frame is None:
            print(f"  Warning: Could not extract frame at time {frame_time}s from {video_path}")
            return None
        
        # Create temporary file for the frame
        temp_dir = tempfile.gettempdir()
        video_name = os.path.splitext(os.path.basename(video_path))[0]
        frame_path = os.path.join(temp_dir, f"{video_name}_frame_{int(frame_time)}.jpg")
        
        # Save frame as JPEG
        cv2.imwrite(frame_path, frame)
        
        return frame_path
        
    except Exception as e:
        print(f"  Warning: Error extracting frame from {video_path}: {str(e)}")
        return None


def batch_upload_videos(folder_path, args, youtube, metadata):
    """
    Upload all MP4 files from a folder with intervals between uploads.

    Args:
        folder_path (str): Path to the folder containing MP4 files
        args: Command line arguments containing video metadata
        youtube: Authenticated YouTube API service
        metadata: Dictionary mapping filename to video metadata
    """
    mp4_files = get_mp4_files(folder_path)

    if not mp4_files:
        print(f"No MP4 files found in {folder_path}")
        return

    print(f"Found {len(mp4_files)} MP4 file(s) to upload")
    print(f"Interval between uploads: {INTERVAL_BETWEEN_UPLOADS} seconds\n")
    
    # Skip files until we reach the start_from file
    start_index = 0
    if hasattr(args, 'start_from') and args.start_from:
        for i, file_path in enumerate(mp4_files):
            if os.path.basename(file_path) == args.start_from:
                start_index = i
                print(f"Starting from file: {args.start_from}\n")
                break
        else:
            print(f"Warning: File '{args.start_from}' not found. Starting from beginning.\n")
    
    mp4_files = mp4_files[start_index:]

    for index, file_path in enumerate(mp4_files, 1):
        file_name = os.path.basename(file_path)
        print(f"[{index}/{len(mp4_files)}] Processing: {file_name}")

        try:
            # Update the file path in args for this upload
            args.file = file_path

            # Set default category and privacy status
            args.category = "27"  # Education
            args.privacyStatus = "public"
            
            # Initialize description and keywords if they don't exist
            if not hasattr(args, 'description'):
                args.description = ""
            if not hasattr(args, 'keywords'):
                args.keywords = ""

            # Look up metadata for this file
            if file_name in metadata:
                file_metadata = metadata[file_name]
                args.title = file_metadata["title"]
                # args.description = file_metadata["description"]
                # args.keywords = file_metadata["tags"]
                print(f"  Title: {args.title}")
            else:
                print(f"  Warning: No metadata found in CSV for {file_name}")
                print(f"  Using default title: {args.title}")
            
            # Extract frame and generate description if description is missing
            print(f"  Extracting frame from video...")
            frame_path = extract_frame_from_video(file_path, frame_time=0)
            
            if frame_path:
                print(f"  Generating description and keywords from frame...")
                try:
                    result = get_image_exercise_text(frame_path)
                    if result and result.get("description"):
                        description = clean_description_for_youtube(result["description"])
                        # Ensure description is not empty
                        if description:
                            args.description = description
                            print(f"  Generated description: {description[:100]}...")
                        else:
                            print(f"  Warning: Generated description is empty after cleaning")
                    if result and result.get("keywords"):
                        # If keywords are not already set, use generated keywords
                        if not args.keywords or args.keywords.strip() == "":
                            args.keywords = result["keywords"]
                            print(f"  Generated keywords: {result['keywords']}")
                    # Clean up temporary frame file
                    try:
                        os.remove(frame_path)
                    except:
                        pass
                except Exception as e:
                    print(f"  Warning: Could not generate description: {str(e)}")
            else:
                print(f"  Warning: Could not extract frame, skipping description generation")

            # Clean and validate description before upload
            args.description = clean_description_for_youtube(args.description)
            
            # YouTube requires non-empty description
            if not args.description or args.description.strip() == "":
                print(f"  Warning: No description available, using default")
                args.description = "הכנה לבגרות במתמטיקה"
            
            # Debug: Print description info before upload
            desc_bytes = len(args.description.encode('utf-8'))
            desc_chars = len(args.description)
            print(f"  Description: {desc_chars} characters, {desc_bytes} bytes")
            
            # Upload the video
            try:
                initialize_upload(youtube, args)
            except Exception as upload_error:
                # If upload fails with description error, try with a minimal description
                if "invalidDescription" in str(upload_error) or "invalid description" in str(upload_error).lower():
                    print(f"  Error: Invalid description detected. Saving problematic description for debugging...")
                    # Save the problematic description to a file for debugging
                    debug_file = os.path.join(tempfile.gettempdir(), f"problematic_description_{file_name}.txt")
                    try:
                        with open(debug_file, 'w', encoding='utf-8') as f:
                            f.write(f"Original description:\n{args.description}\n\n")
                            f.write(f"Bytes: {desc_bytes}, Characters: {desc_chars}\n")
                            f.write(f"First 100 chars: {repr(args.description[:100])}\n")
                        print(f"  Saved problematic description to: {debug_file}")
                    except:
                        pass
                    # Try with a minimal safe description
                    original_desc = args.description
                    args.description = "הכנה לבגרות במתמטיקה"
                    print(f"  Retrying with minimal description...")
                    try:
                        initialize_upload(youtube, args)
                        print(f"  Success with minimal description")
                    except:
                        args.description = original_desc
                        raise upload_error
                else:
                    raise upload_error

            # Wait before uploading the next file (except for the last one)
            if index < len(mp4_files):
                print(
                    f"Waiting {INTERVAL_BETWEEN_UPLOADS} seconds before next upload...\n"
                )
                time.sleep(INTERVAL_BETWEEN_UPLOADS)
            else:
                print("\nAll videos uploaded successfully!")

        except Exception as e:
            print(f"Error uploading {file_name}: {str(e)}\n")
            print(f"Description: {args.description}")
            print(f"Keywords: {args.keywords}")
            print(f"Title: {args.title}")
            # continue
            raise e


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Batch upload all MP4 files from a folder to YouTube"
    )
    parser.add_argument(
        "--folder", required=True, help="Folder path containing MP4 files to upload"
    )
    parser.add_argument(
        "--csv",
        help="Path to CSV file containing video metadata",
        default="vb_media.csv",
    )
    parser.add_argument(
        "--playlist-id",
        required=True,
        help="YouTube playlist ID to add uploaded videos to",
    )
    parser.add_argument(
        "--start-from",
        help="Filename to start uploading from (skips all files before this one)",
        default="",
    )

    args = parser.parse_args()

    # Validate folder path
    if not os.path.isdir(args.folder):
        exit(f"Error: Folder '{args.folder}' does not exist.")

    # Load video metadata from CSV
    metadata = load_video_metadata(args.csv)

    # Get authenticated YouTube service
    youtube = get_authenticated_service(args)

    # Start batch upload
    try:
        batch_upload_videos(args.folder, args, youtube, metadata)
    except Exception as e:
        print(f"Batch upload failed: {str(e)}")
        exit(1)
