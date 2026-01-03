#!/usr/bin/python

import os
import sys
import time
import glob
import argparse
import csv
from pathlib import Path

# Add parent directory to path to import upload_video module
sys.path.insert(0, os.path.dirname(__file__))

from upload_video import (
    get_authenticated_service,
    initialize_upload,
    VALID_PRIVACY_STATUSES,
)

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
                filename = row["filename"]
                metadata[filename] = {
                    "title": row["title"]
                    .replace("שאלון 803 - ", "")
                    .replace("שאלון 804 - ", "")
                    .replace("שאלון 804 ו 803 - ", "")
                    .replace("שאלון 805 -", "")
                    .replace("שאלון 805 ושאלון 807 - ", "")
                    .replace("שאלון 807 ושאלון 805 - ", "")
                    .replace("שאלון 806 -", "")
                    .replace("שאלון 803, 804 ו 806 - ", "")
                    .replace("שאלון 807 -", "")
                    .replace("שאלון 803", "")
                    .strip(),
                    "description": row["description"],
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

    for index, file_path in enumerate(mp4_files, 1):
        file_name = os.path.basename(file_path)
        print(f"[{index}/{len(mp4_files)}] Processing: {file_name}")

        try:
            # Update the file path in args for this upload
            args.file = file_path

            # Set default category and privacy status
            args.category = "27"  # Education
            args.privacyStatus = "public"

            # Look up metadata for this file
            if file_name in metadata:
                file_metadata = metadata[file_name]
                args.title = file_metadata["title"]
                args.description = file_metadata["description"]
                args.keywords = file_metadata["tags"]
                print(f"  Title: {args.title}")
            else:
                print(f"  Warning: No metadata found in CSV for {file_name}")
                print(f"  Using default title: {args.title}")

            # Upload the video
            initialize_upload(youtube, args)

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
            continue


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
