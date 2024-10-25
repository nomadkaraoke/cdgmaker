import logging
import re
import toml
import argparse
from pathlib import Path
from cdgmaker.composer import KaraokeComposer
import sys
from PIL import ImageFont, Image
from cdgmaker.render import get_wrapped_text

# Constants for TOML configuration
CLEAR_MODE = "eager"
BACKGROUND_COLOR = "#111427"
BORDER_COLOR = "#ff7acc"
FONT_SIZE = 16
STROKE_WIDTH = 1
STROKE_STYLE = "octagon"
ACTIVE_FILL = "#7070F7"
ACTIVE_STROKE = "#1A3AEB"
INACTIVE_FILL = "#ffaacc"
INACTIVE_STROKE = "#880066"

CDG_VISIBLE_WIDTH = 288  # Maximum width in pixels for CDG
TITLE_COLOR = "#ffffff"
ARTIST_COLOR = "#ffdf6b"

FONT = "/Users/andrew/AvenirNext-Bold.ttf"
TITLE_SCREEN_BACKGROUND = "/Users/andrew/cdg-title-screen-background-nomad-simple.png"

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Add new constants for default values
DEFAULT_ROW = 4  # Increased from 1 to move text lower
DEFAULT_LINE_TILE_HEIGHT = 3
DEFAULT_LINES_PER_PAGE = 4


def parse_lrc(lrc_file):
    with open(lrc_file, "r", encoding="utf-8") as f:
        content = f.read()

    # Extract timestamps and lyrics
    pattern = r"\[(\d{2}):(\d{2})\.(\d{3})\](\d+:)?(/?.*)"
    matches = re.findall(pattern, content)

    if not matches:
        raise ValueError(f"No valid lyrics found in the LRC file: {lrc_file}")

    lyrics = []
    for match in matches:
        minutes, seconds, milliseconds = map(int, match[:3])
        timestamp = (minutes * 60 + seconds) * 100 + int(milliseconds / 10)  # Convert to centiseconds
        text = match[4].strip()
        if text:  # Only add non-empty lyrics
            lyrics.append({"timestamp": timestamp, "text": text})
            logger.debug(f"Parsed lyric: {timestamp} - {text}")

    logger.info(f"Found {len(lyrics)} lyric lines")
    return lyrics


def generate_toml(lrc_file, audio_file, title, artist, output_file, row, line_tile_height, lines_per_page, title_color, artist_color):
    try:
        lyrics_data = parse_lrc(lrc_file)
    except ValueError as e:
        logger.error(f"Error parsing LRC file: {e}")
        return

    if not lyrics_data:
        logger.error(f"No lyrics data found in the LRC file: {lrc_file}")
        return

    formatted_lyrics = format_lyrics(lyrics_data)
    print(formatted_lyrics)

    sync_times = [lyric["timestamp"] for lyric in lyrics_data]
    for lyric in lyrics_data:
        logger.debug(f"Sync time: {lyric['timestamp']} for lyric: {lyric['text']}")

    toml_data = {
        "title": title,
        "artist": artist,
        "file": audio_file,
        "outname": Path(lrc_file).stem,
        "clear_mode": CLEAR_MODE,
        "sync_offset": 0,
        "background": BACKGROUND_COLOR,
        "border": BORDER_COLOR,
        "font": FONT,
        "font_size": FONT_SIZE,
        "stroke_width": STROKE_WIDTH,
        "stroke_style": STROKE_STYLE,
        "singers": [
            {"active_fill": ACTIVE_FILL, "active_stroke": ACTIVE_STROKE, "inactive_fill": INACTIVE_FILL, "inactive_stroke": INACTIVE_STROKE}
        ],
        "lyrics": [
            {
                "singer": 1,
                "sync": sync_times,
                "row": row,
                "line_tile_height": line_tile_height,
                "lines_per_page": lines_per_page,
                "text": formatted_lyrics,
            }
        ],
        "title_color": title_color,
        "artist_color": artist_color,
        "title_screen_background": TITLE_SCREEN_BACKGROUND,
    }

    with open(output_file, "w", encoding="utf-8") as f:
        toml.dump(toml_data, f)

    logger.info(f"TOML file generated: {output_file}")
    logger.debug(f"Generated TOML data: {toml_data}")


def get_font():
    try:
        return ImageFont.truetype(FONT, FONT_SIZE)
    except IOError:
        logger.warning(f"Font file {FONT} not found. Using default font.")
        return ImageFont.load_default()


def get_text_width(text, font):
    return font.getmask(text).getbbox()[2]


def wrap_text(text, max_width, font):
    words = text.split()
    lines = []
    current_line = []
    current_width = 0

    for word in words:
        word_width = get_text_width(word, font)
        if current_width + word_width <= max_width:
            current_line.append(word)
            current_width += word_width + get_text_width(" ", font)
        else:
            if current_line:
                lines.append(" ".join(current_line))
                logger.debug(f"Wrapped line: {' '.join(current_line)}")
            current_line = [word]
            current_width = word_width

    if current_line:
        lines.append(" ".join(current_line))
        logger.debug(f"Wrapped line: {' '.join(current_line)}")

    return lines


def format_lyrics(lyrics_data):
    formatted_lyrics = []
    font = get_font()
    logger.debug(f"Using font: {font}")

    current_line = ""
    for lyric in lyrics_data:
        text = lyric["text"]
        logger.debug(f"Original lyric text: {text}")

        if text.startswith("/"):
            # Start a new line when encountering a slash
            if current_line:
                wrapped_text = get_wrapped_text(current_line.strip(), font, CDG_VISIBLE_WIDTH)
                logger.debug(f"Wrapped text: {wrapped_text}")
                formatted_lyrics.extend(wrapped_text.split("\n"))
                current_line = ""
            text = text[1:]

        current_line += text + " "

    # Wrap and add the last line if it exists
    if current_line:
        wrapped_text = get_wrapped_text(current_line.strip(), font, CDG_VISIBLE_WIDTH)
        logger.debug(f"Wrapped text: {wrapped_text}")
        formatted_lyrics.extend(wrapped_text.split("\n"))

    # Add empty lines where appropriate
    final_lyrics = []
    for line in formatted_lyrics:
        final_lyrics.append(line)
        logger.debug(f"Added line to final_lyrics: {line}")
        if line.endswith(("!", "?", ".")):
            final_lyrics.append("~")
            logger.debug("Added empty line after punctuation")

    result = "\n".join(final_lyrics)
    logger.debug(f"Final formatted lyrics:\n{result}")
    return result


def main(lrc_file, audio_file, title, artist, row, line_tile_height, lines_per_page, title_color, artist_color):
    toml_file = f"{Path(lrc_file).stem}.toml"
    generate_toml(lrc_file, audio_file, title, artist, toml_file, row, line_tile_height, lines_per_page, title_color, artist_color)

    # Run cdgmaker
    try:
        kc = KaraokeComposer.from_file(toml_file)
        kc.compose()
        logger.info("CDG file generated successfully")
    except Exception as e:
        logger.error(f"Error composing CDG: {e}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Convert LRC file to CDG")
    parser.add_argument("lrc_file", help="Path to the LRC file")
    parser.add_argument("audio_file", help="Path to the audio file")
    parser.add_argument("--title", required=True, help="Title of the song")
    parser.add_argument("--artist", required=True, help="Artist of the song")
    parser.add_argument("--row", type=int, default=DEFAULT_ROW, help="Starting row for lyrics (0-17)")
    parser.add_argument("--line-tile-height", type=int, default=DEFAULT_LINE_TILE_HEIGHT, help="Height of each line in tile rows")
    parser.add_argument("--lines-per-page", type=int, default=DEFAULT_LINES_PER_PAGE, help="Number of lines per page")
    parser.add_argument("--title-color", default=TITLE_COLOR, help="Color of the title text on the intro screen")
    parser.add_argument("--artist-color", default=ARTIST_COLOR, help="Color of the artist text on the intro screen")

    # If no arguments are provided, print help and exit
    if len(sys.argv) == 1:
        parser.print_help(sys.stderr)
        sys.exit(1)

    args = parser.parse_args()

    main(
        args.lrc_file,
        args.audio_file,
        args.title,
        args.artist,
        args.row,
        args.line_tile_height,
        args.lines_per_page,
        args.title_color,
        args.artist_color,
    )
