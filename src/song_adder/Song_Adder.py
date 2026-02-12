import io
import json
import logging
import os
import sys
import tkinter as tk
from json import JSONDecodeError
from logging import Logger, LogRecord
from pathlib import Path
from tkinter import Tk, filedialog
from typing import Any, Callable, cast

from metadata_utils.CF_Program import (
    Song,
    get_song_data,
    process_new_tags,
    set_tags,
)
from metadata_utils.data_verification import ValidationError, validate_payload
from metadata_utils.engraver import build_payload, engrave_payload
from metadata_utils.hash_mutagen import get_audio_hash
from mutagen.id3 import APIC, ID3
from PIL import Image, ImageTk, UnidentifiedImageError
from PIL.ImageFile import ImageFile

from .remuxer import remux_song

logger = logging.getLogger(__name__)


class App():
    def __init__(self, script_dir: Path):

        sys.stderr = StreamToLogger(logger, logging.CRITICAL)

        self.main_window = tk.Tk()
        self.colors: dict[str, str] = self.load_colors(script_dir)
        self.song_path: (str | None) = None
        self.song_data: (dict[str, str] | None) = None
        self.song_obj: (Song | None) = None
        self.save_folder: (str | None) = None
        self.new_payload_preview: (str | None) = None # JSON-Formatted string

    def main(self) -> None:
        self.build_ui()
        self.main_window.configure(bg=self.colors["primary"])
        self.main_window.minsize(1100, 600)
        self.main_window.title("Song Adder")
        self.main_window.protocol("WM_DELETE_WINDOW", self.closing_protocol)
        logger.info(f"{'-'*30} Program Start {'-'*30}")
        self.main_window.mainloop()

    def build_ui(self) -> None:
        #self.main_window = tk.Tk()

        self.adder_frame = Adder_Frame(
            master=self.main_window,
            colors=self.colors,
            load_preview_callback=self.load_preview,
            generate_callback=self.generate_file)

        self.preview_frame = Preview_Frame(master=self.main_window, colors=self.colors)

        self.options_frame = Options_Frame(
            master=self.main_window, 
            colors=self.colors,
            load_file_callback=self.load_file,
            folder_callback=self.folder_selection_dialog)

        self.separator = tk.Frame(master=self.main_window, bg=self.colors['secondary text'])

        self.image_frame = Image_Frame(
            master=self.main_window, colors=self.colors)

        self.info_frame = Info_Frame(master=self.main_window, colors=self.colors)

        self.options_frame.grid(row=0, column=0, columnspan=3, sticky = 'w')
        self.separator.grid(row=1, column=0, columnspan=3, sticky='we', pady=(0, 10))
        self.adder_frame.grid(row=2, column=0,rowspan=2, sticky='nw')
        self.image_frame.grid(row=2, column=1, sticky='nw')
        self.preview_frame.grid(row=2, column=2, sticky='n')
        self.info_frame.grid(row=3, column=1, columnspan=2, sticky='nw')

    def load_colors(self, script_dir: Path) -> dict[str, str]:

        DEFAULT_COLORS = {
                    "primary" : "#1A1423",
                    "secondary": "#4A3164",
                    "text" : "white",
                    "secondary text" : "#2C943A"
                    }
        
        color_config = script_dir / "color_config.json"

        if not os.path.exists(color_config):
            logger.debug("No color_config found, loading default colors")
            return DEFAULT_COLORS

        try:
            with open(color_config, "r") as file:
                color_palette = json.load(file)
            if self._is_valid_theme_format(color_palette) and self._are_valid_colors(color_palette):
                return color_palette
            else:
                logger.debug("color validation failed, loading default colors instead")
                return DEFAULT_COLORS

        except Exception as e:
            logger.debug(e)
            logger.warning("Failed loading custom theme colors!")
            return DEFAULT_COLORS            

    def _is_valid_theme_format(self, data: Any) -> bool:
        REQUIRED_KEYS = ["primary", "secondary", "text", "secondary text"]
        
        if not isinstance(data, dict):
            return False
        
        return all(key in data and isinstance(data[key], str) for key in REQUIRED_KEYS)

    def _are_valid_colors(self, custom_colors: dict[str, str]) -> bool:
        REQUIRED_KEYS = ["primary", "secondary", "text", "secondary text"]
        for color_string in [custom_colors[key] for key in REQUIRED_KEYS]:
            try:
                self.main_window.winfo_rgb(color_string)
            except tk.TclError:
                logger.debug(f'"{color_string}" is not a valid color')
                return False
        else:
            return True

    def load_file(self) -> None:
        self.song_path = self.open_file_dialog()
        audio_tags = self.new_payload_preview = self.song_data = None
        self.options_frame.update_selected_file(self.song_path)

        if self.song_path:
            _, self.song_data, audio_tags = get_song_data(self.song_path)
            self.preview_frame.clear()

            if audio_tags:
                self.image_frame.load_image_binary(audio_tags)
            else:
                self.image_frame.clear_image()

        if self.song_data is not None:
            self.adder_frame.update_entries(self.song_data)

    @staticmethod
    def _truncate_string(string: str, width: int) -> str:
        return ((string[:width-2] + '...') if len(string) > width else string)

    def load_tags_preview(self) -> None:
        new_data = self.adder_frame.get_entries_dict()

        if not self.song_path:
            return

        self.song_obj = Song(self.song_path)
        process_new_tags(self.song_obj, new_data)

        broken_title = self.song_obj.filename.replace(" - ", "\n                                ")

        preview_content = f"""\
        Filename: {broken_title if len(self.song_obj.filename) > 70 else self.song_obj.filename}
        [TIT2] {self.song_obj.title}
        [TPE1] {self.song_obj.artist}
        [COMM::eng] {App._truncate_string(self.song_obj.comment, 50)}
        [TDRC] {self.song_obj.comment[:4]}
        [TPE2] QueenPb + Vedal987
        [TRCK] {self.song_obj.track}
        [TALB] {self.song_obj.album}
        [TPOS] {self.song_obj.album.replace("Disc ", "")}"""

        self.preview_frame.update_tags_label(preview_content)

        logger.debug(f"Tags Preview Loaded:\n\n{preview_content}")
        
    def load_preview(self) -> None:

        ARG_MAP = {
            "Date": "date",
            "Title": "title",
            "Artist": "artist",
            "CoverArtist": "cover_artist",
            "Version": "version",
            "Discnumber": "disc_number",
            "Track": "track",
            "Comment": "comment",
            "Special": "special",
        }

        if not self.song_path:
            logger.warning("No path selected!")
            return

        self.new_payload_preview = self.song_obj = None

        payload_kwargs = {
        ARG_MAP[field]: self.adder_frame.entries[field].get() for field in self.adder_frame.FIELD_NAMES
        }
    
        payload_kwargs["filename"] = os.path.basename(self.song_path)

        temp_hash = get_audio_hash(self.song_path)
        if temp_hash is None:
            logger.critical("The program was unable to generate a hash")
            return
        else:
            payload_kwargs["xxhash"] = temp_hash

        try:
            validate_payload(payload_kwargs)
            self.new_payload_preview = build_payload(**payload_kwargs)     

        except ValidationError as e:
            logger.warning(e)

        except Exception as e:
            logger.debug(payload_kwargs)
            logger.exception(e)

        else:
            self.preview_frame.update_new_payload(self.new_payload_preview)
            self.load_tags_preview()

    def generate_file(self) -> None:

        if (not self.song_obj or not self.new_payload_preview):
            logger.warning("Either no song selected or no preview!")
            return
        elif not self.save_folder:
            logger.warning("Please select a save folder!")
            return

        new_path = os.path.join(self.save_folder, self.song_obj.filename)

        remux_song(file_path=str(self.song_obj.path), new_path=new_path)
        logger.debug(f"Remuxed song created at {new_path}")

        image_data = self.image_frame.read_image_data()
        image_type = None

        if image_data is not None:
            _, image_type = os.path.splitext(str(self.image_frame.cover_path))

            image_type = image_type.replace(".", "")

            if image_type == "jpg":
                image_type = "jpeg" 

        set_tags(new_path, self.song_obj, image_type, image_data)
        logger.debug("ID3v2 tags added")

        engrave_payload(new_path, self.new_payload_preview)
        logger.debug("Json payload added")

        logger.info(f"Finished processing of {self.song_obj.filename}!")

    def open_file_dialog(self) -> str | None:
        """Opens a file selection dialog and returns the selected file path."""

        file_path = filedialog.askopenfilename(
            title="Choose a file",
            initialdir= os.path.dirname(self.song_path) if self.song_path else "/",
            filetypes=(
                ("MP3 files", "*.MP3"),
                ("All files", "*.*")
            )
        )
        if file_path:
            logger.debug(f"Selected file path: {file_path}")
            return file_path
        logger.debug("No file path selected")

    def folder_selection_dialog(self) -> None:
        """Opens a file selection dialog and returns the selected file path."""

        folder_path = filedialog.askdirectory(
            title="Select a Destination Folder",
            initialdir=os.path.dirname(self.save_folder) if self.save_folder else "/"
        )
        if folder_path:
            logger.debug(f"Selected folder path: {folder_path}")
            self.save_folder = folder_path
        else:
            logger.debug("No folder path selected")

        self.options_frame.update_selected_folder(folder_path)

    def closing_protocol(self) -> None:
        logger.debug("Closing program without issues")
        self.main_window.destroy()

class Adder_Frame(tk.Frame):
    def __init__(self, 
                master: Tk, colors: dict[str, str], 
                load_preview_callback: Callable[[], None],
                generate_callback: Callable[[], None], 
                **kwargs: Any
                ):
        super().__init__(master ,width=350, height=520, padx=10, pady=10, bg=colors['primary'], **kwargs)

        self.grid_propagate(False)
        self.columnconfigure(0, weight=1)

        self.entries : dict[str, tk.Entry] = {}

        self.FIELD_NAMES = [
            "Date", "Title", "Artist", "CoverArtist", 
            "Version", "Discnumber", "Track", "Comment",
            "Special"
        ]

        self._build_frame(load_preview_callback=load_preview_callback, colors=colors)

        preview_button = tk.Button(
            master=self,
            text="Preview",
            width=20, 
            command=load_preview_callback,
            fg=colors["secondary text"],
            bg=colors["secondary"]
        )
        preview_button.grid(row=18, column=0, sticky="w", padx=8, pady=(30, 0))

        generate_file_button = tk.Button(
            master=self,
            text="Generate File",
            width=20, 
            command=generate_callback,
            fg=colors["secondary text"],
            bg=colors["secondary"]
        )
        generate_file_button.grid(row=19, column=0, sticky="w", padx=8, pady=4)

    def _build_frame(self, load_preview_callback: Callable[[], None], colors: dict[str,str]) -> None:
    
        i = 0 
        for name in self.FIELD_NAMES:
            self.columnconfigure(0, weight=1) # Makes column 0 stretchable
            # 1. Create and place the Label
            label = tk.Label(
                master=self,
                text=f"{name}:",
                bg=colors["primary"],
                fg=colors['text']
                )
            label.grid(row=i, column=0, sticky="w", padx=(15, 0), pady=1)
            i += 1
            entry = tk.Entry(
                master=self,
                width=50,
                fg=colors["secondary text"],
                bg=colors["secondary"]
                )
            entry.grid(row=i, column=0, sticky="w", padx=8, pady=1)
            
            self.entries[name] = entry

            i += 1

    def get_entries_dict(self) -> dict[str, str]:
        return {key: self.entries[key].get() for key in self.entries}

    def update_entries(self, song_data: dict[str,str]) -> None:
        for field in song_data:
            if field == "xxHash":
                continue
            self.entries[field].delete("0", tk.END)
            self.entries[field].insert("0", song_data[field])

class Options_Frame(tk.Frame):

    def __init__(
        self, master: Tk, colors: dict[str, str], 
        load_file_callback: Callable[[], None], folder_callback: Callable[[], None], 
        **kwargs: Any
        ):
        super().__init__(master, padx=20, pady=10, bg=colors["primary"], **kwargs)

        open_button = tk.Button(
            master=self,
            text="Load File",
            command=load_file_callback,
            fg=colors["secondary text"],
            bg=colors["secondary"]
            )
        open_button.grid(row=0, column=0)

        Save_folder_button = tk.Button(
            master=self,
            text="Select Save Folder",
            command=folder_callback,
            fg=colors["secondary text"],
            bg=colors["secondary"]
            )
        Save_folder_button.grid(row=0, column=1)

        self.selected_file_label = tk.Label(
            master=self,
            text="Selected File: ",
            fg=colors["text"],
            bg=colors["primary"]
        )
        self.selected_file_label.grid(row=0, column=2, sticky="nw", padx=(20, 0))

        self.selected_folder_label = tk.Label(
            master=self,
            text="Selected Folder: ",
            fg=colors["text"],
            bg=colors["primary"],
        )
        self.selected_folder_label.grid(row=1, column=2, sticky="nw", padx=(20, 0))

    def update_selected_file(self, string: (str | None)) -> None:
        if string is None:
            string = ''
        
        string = self._truncate_path(string)

        self.selected_file_label['text'] = f"Selected File: {string}"

    def update_selected_folder(self, string: (str | None)) -> None:
        if string is None:
            string = ''

        string = self._truncate_path(string)

        self.selected_folder_label['text'] = f"Selected Folder: {string}"

    def _truncate_path(self, string: str) -> str:
        MAXIMUM_LENGTH = 150

        string_size = len(string)
        if string_size > MAXIMUM_LENGTH:
            string = string[string_size - MAXIMUM_LENGTH - 1:]
            string = '~/'+string
        return string

class Preview_Frame(tk.Frame):
    def __init__(self, master: Tk, colors: dict[str, str], **kwargs: Any):
        super().__init__(master, width=500, height=375, padx=5, pady=5, bg=colors['primary'], **kwargs)
        
        self.grid_propagate(False)
        self.columnconfigure(0, weight=1)

        self.new_payload_label = tk.Label(
            self,
            text="New Payload:\n",
            justify="left",
            bg=colors['primary'],
            fg=colors['text'])

        self.new_payload_label.grid(row=0, column=0, sticky='nw')

        self.new_tags_label = tk.Label(self,
        text="New Tags Preview:\n",
        justify="left",
        bg=colors['primary'],
        fg=colors['text'])
        self.new_tags_label.grid(row=1, column=0, sticky='nw')

    def update_new_payload(self, new_payload: str) -> None:
        new_payload_data = {}
        try:
            new_payload_data = json.loads(new_payload)
        except JSONDecodeError as e:
            logger.error("File couldn't be processed! Error decoding the comment!")
            logger.debug(e)

        self.new_payload_label['text'] = f"""\
New Payload:\n
        Date: {new_payload_data["Date"]}        
        Title: {new_payload_data["Title"]}
        Artist: {new_payload_data["Artist"]}
        CoverArtist: {new_payload_data["CoverArtist"]}
        Version: {new_payload_data["Version"]}
        Discnumber: {new_payload_data["Discnumber"]}
        Track: {new_payload_data["Track"]}
        Comment: {new_payload_data["Comment"]}
        Special: {new_payload_data["Special"]}
"""

        logger.debug(f"Payload Preview Loaded: {self.new_payload_label['text']}")
    
    def update_tags_label(self, tags_text: str) -> None:
        self.new_tags_label['text'] = f"New Tags Preview:\n{tags_text}"

    def clear(self) -> None:
        self.new_payload_label['text'] = "New Payload:\n"
        self.new_tags_label['text'] = "New Tags Preview:\n"

class Image_Frame(tk.Frame):
    def __init__(self, master: Tk, colors: dict[str, str], **kwargs: Any):
        super().__init__(master,width=300, height=300, padx=10, pady=10, bg=colors["secondary"], **kwargs)
        
        #self.pack_propagate(False)

        self.cover_path: str | None = None
        self.cover_folder: str = '/'

        self.placeholder = tk.PhotoImage(width=300, height=300)

        self.image_label = tk.Label(
            self,
            image=self.placeholder,
            bg='darkgray',
            bd=0
            )
        self.image_label.pack(anchor="nw",fill="both", expand=True)
        self.image_label.bind("<Button-1>", self.on_image_click)

    def load_image_binary(self, audio_tags: ID3) -> None:
        try:
            apic_frames = cast(list[APIC], audio_tags.getall("APIC"))

            if not apic_frames:
                logger.debug("No image found")
                self.clear_image()
                return

            binary_data = getattr(cast(bytes, apic_frames[0]), "data")
            image_stream = io.BytesIO(binary_data)
            img_open = Image.open(image_stream)

        except Exception as e:
            logger.error("Failed reading embedded image data")
            logger.debug(e)

        else:
            self._load_image(img_open)

    def _load_image(self, img: ImageFile) -> None:
        resized_img = img.resize((300, 300))
        tk_img = ImageTk.PhotoImage(resized_img)

        self.image_label.config(image=tk_img)
        setattr(self.image_label, "image", tk_img)

    def _cover_selection_dialog(self) -> (str | None):
        """Opens a file selection dialog and returns the selected file path."""

        file_path = filedialog.askopenfilename(
            title="Choose a file",
            initialdir=self.cover_folder if self.cover_folder else "/",
            filetypes=(
                ("Image files", "*.png;*.jpg;*.jpeg"),
            )
        )
        if file_path:
            logger.debug(f"Selected image path: {file_path}")
            self.cover_path = file_path
            self.cover_folder = os.path.dirname(file_path)
            return file_path
        else:
            logger.debug("No image path selected")

    def on_image_click(self, event: Any) -> None:
        img_path = self._cover_selection_dialog()
        if not img_path:
            return

        try:
            img_open = Image.open(img_path)

        except UnidentifiedImageError:
            logger.error("Invalid image, please select another one!")
            
        else:
            self._load_image(img_open)

    def read_image_data(self) -> (bytes | None):
        if not self.cover_path:
            return None

        try:
            with open(self.cover_path, 'rb') as new_cover:
                image_data = new_cover.read()
            return image_data
                
        except Exception as e:
            logger.error("Failed reading image data")
            logger.debug(e)

    def clear_image(self) -> None:
        self.image_label.config(image=self.placeholder)
        setattr(self.image_label, "image", self.placeholder)

class Info_Frame(tk.Frame):
    def __init__(self, master: Tk, colors: dict[str, str], **kwargs: Any):
        super().__init__(master, width=820, height=100, **kwargs)

        self.info_label = tk.Text(
            self,
            state='disabled',
            width=97,
            height=9,
            wrap="word",
            fg=colors["secondary text"],
            bg=colors["secondary"])

        self.info_label.grid(row=0, column=0, sticky='nw')

        # --- Setup Scrollbar ---
        self.scrollbar = tk.Scrollbar(self, command=self.info_label.yview, bg=colors["secondary"]) # type: ignore
        self.scrollbar.grid(row=0, column=1, sticky='ns')

        # --- Link them together ---
        self.info_label['yscrollcommand'] = self.scrollbar.set

        self.gui_handler = logging.StreamHandler(Redirector(self.info_label))
        self.gui_handler.setFormatter(GuiFormatter())
        self.gui_handler.setLevel(logging.INFO)

        logger.addHandler(self.gui_handler)

class GuiFormatter(logging.Formatter):
    def format(self, record: LogRecord):
        # 1. Handle your stderr redirection (CRITICAL level)
        if record.levelno == logging.CRITICAL:
            return "An internal error occurred. Please check the logs."
        
        # 2. Handle INFO level: return only the message, no level name
        if record.levelno == logging.INFO:
            return record.getMessage()
            
        # 3. Handle everything else (WARNING, ERROR, etc.)
        # This keeps the "LEVEL: message" format for important alerts
        return f"{record.levelname}: {record.getMessage()}"

class Redirector:
    def __init__(self, widget: tk.Text):
        self.widget = widget

    def write(self, string: str):
        # 1. Enable editing so we can write to it
        self.widget.configure(state='normal')
        
        # 2. Insert the text
        self.widget.insert("end", string)
        
        # 3. Auto-scroll to the bottom
        self.widget.see("end")
        
        # 4. Disable editing again so the user cannot type/delete
        self.widget.configure(state='disabled')

    def flush(self):
        pass

class StreamToLogger:
    """
    Fake file-like stream object that redirects writes to a logger instance.
    """
    def __init__(self, logger: Logger, log_level: Any):
        self.logger = logger
        self.log_level = log_level

    def write(self, buf: Any):
        for line in buf.rstrip().splitlines():
            self.logger.log(self.log_level, line.rstrip())

    def flush(self):
        pass

