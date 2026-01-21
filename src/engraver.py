from pathlib import Path
from typing import Any, cast

from mutagen.id3 import COMM, ID3
from mutagen.mp3 import MP3


def get_all_mp3(directory: str) -> list[str]: 
    """
    Function that gathers all mp3 files from a directory.
    """
    p = Path(directory)
    return [(str(f)) for f in p.rglob('*.mp3') if f.is_file()]

# Get comment

def get_tag_value(tags: ID3, tag: str) -> (str | None) :
    frame = cast(Any, tags.get(tag))
    if frame is not None:
        return getattr(frame, 'text', None)

def get_content_from_tags(all_tags: ID3, tag: str) -> str:
    content_value = get_tag_value(all_tags, tag)
    if content_value is not None:
        content_text = str(content_value[0])
        return content_text
            
    return ""

def build_payload(filename: str, date: str, title: str, artist: str, 
                  cover_artist: str, version: str, disc_number: str,
                  track: str, comment: str, special: str, xxhash: str
                 ) -> str:

    comm_ved = "{"
    if date:
        comm_ved += f"\"Date\":\"{date}\","
    else:
        raise Exception(f"No date for {filename}!")

    if title:
        comm_ved += f"\"Title\":\"{title}\","
    else:
        raise Exception(f"No title for {filename}!")

    if artist:
        comm_ved += f"\"Artist\":\"{artist}\","
    else:
        raise Exception(f"No artist for {filename}!")

    if cover_artist:
        comm_ved += f"\"CoverArtist\":\"{cover_artist}\","
    else:
        raise Exception(f"No cover_artist for {filename}!")

    if version:
        comm_ved += f"\"Version\":\"{version}\","
    else:
        raise Exception(f"No version for {filename}!")

    if disc_number:
        comm_ved += f"\"Discnumber\":\"{disc_number}\","
    else:
        raise Exception(f"No disc number for {filename}!")

    if track:
        comm_ved += f"\"Track\":\"{track}\","
    else:
        raise Exception(f"No track for {filename}!")

    if comment:
        comm_ved += f"\"Comment\":\"{comment}\","
    else:
        comm_ved += "\"Comment\":\"None\","

    comm_ved += f"\"Special\":\"{special}\","

    if xxhash:
        comm_ved += f"\"xxHash\":\"{xxhash}\"}}"
    else:
        raise Exception(f"No hash for {filename}!")

    return comm_ved

def engrave_payload(path: str, song_data: str) -> None:

    audio = MP3(path, ID3=ID3)
    
    if audio.tags is None:
        audio.add_tags()

    NEW_COMM_VED_FRAME = COMM(encoding=3,lang='ved', desc='',text=[song_data])

    assert audio.tags is not None
    audio.tags.add(NEW_COMM_VED_FRAME)

    audio.save()

    #print(f"Payload added to {os.path.basename(path)}")
