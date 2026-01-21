
import xxhash
from mutagen.id3 import ID3, ID3NoHeaderError


def get_audio_hash(file_path: str) -> (str | None):
    try:
        try:
            audio_tags = ID3(file_path)
            header_size = audio_tags.size  # Mutagen provides the full tag size including header
        except ID3NoHeaderError:
            header_size = 0

        with open(file_path, 'rb') as f:
            # We read the whole file to handle the footer check
            # For very large files, you can use f.seek() instead of loading everything
            file_data = f.read()

        # 2. Check for ID3v1 footer (always 128 bytes at the end starting with 'TAG')
        footer_size = 128 if file_data[-128:].startswith(b'TAG') else 0
        
        # 3. Slice the data to extract only the audio frames
        # If footer_size is 0, file_data[header_size:] takes everything to the end
        end_index = len(file_data) - footer_size
        raw_audio = file_data[header_size:end_index]

        # 4. Hash the raw audio
        return xxhash.xxh64(raw_audio).hexdigest()

    except Exception as e:
        print(f"Error processing {file_path}: {e}")
        return None
