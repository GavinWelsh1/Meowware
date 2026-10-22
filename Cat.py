import base64
import ctypes
import ctypes.util
import io
import math
import random
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from PIL import Image

try:
	import pygame
except ImportError:
	pygame = None


class DesktopCat:
	def __init__(self, root):
		self.root = root
		self.root.title("Desktop Cat")
		self.root.geometry("760x680")
		self.root.minsize(700, 640)
		self.root.configure(bg="#f2efe8")

		self.annoyance = 0
		self.annoyance_limit = 100
		self.cat_x = 180
		self.cat_y = 170
		self.dx = 2.8
		self.dy = 2.1
		self.simulate_shutdown = tk.BooleanVar(value=True)
		self.prank_enabled = tk.BooleanVar(value=True)
		self.avatar_visible = tk.BooleanVar(value=True)
		self.shutdown_window = None
		self.avatar_window = None
		self.avatar_displayed_image = None
		self.avatar_canvas_size = (150, 150)
		self.sound_paths = []
		asset_dir = Path(__file__).resolve().parent
		self.nyan_music_path = asset_dir / "nyan_cat_compressed.mp3"
		self.meme_images = []
		self.nyan_frames = []
		self.nyan_window = None
		self.nyan_label = None
		self.nyan_x = 0
		self.nyan_y = 0
		self.nyan_frame_index = 0
		self.nyan_frame_ticks = 0
		self.nyan_speed = 12
		meme_load_errors = []
		for path in sorted(asset_dir.glob("meme*.jp*g")):
			try:
				with Image.open(path) as source:
					image = source.convert("RGB")
				image.thumbnail((260, 260), Image.Resampling.LANCZOS)
				self.meme_images.append(self._photo_from_image(image))
			except (OSError, tk.TclError) as error:
				meme_load_errors.append(f"{path.name}: {error}")
		nyan_path = asset_dir / "nyan-cat-original.gif"
		if nyan_path.is_file():
			try:
				with Image.open(nyan_path) as source:
					for frame_index in range(getattr(source, "n_frames", 1)):
						source.seek(frame_index)
						frame = source.convert("RGBA")
						frame.thumbnail((240, 135), Image.Resampling.LANCZOS)
						self.nyan_frames.append(self._photo_from_image(frame))
			except (OSError, tk.TclError) as error:
				self.root.after_idle(
					lambda load_error=str(error): messagebox.showwarning(
						"Nyan Cat animation unavailable",
						f"Could not load {nyan_path.name}: {load_error}",
					)
				)
		self.meme_windows = {}
		default_effect_files = {
			"happy": ("happy-happy-happy-cat.mp3", "happy.mp3", "happy.wav"),
			"irritated": (
				"when-someone-is-suspicious.mp3",
				"irritated.mp3",
				"irritated.wav",
			),
			"mad": ("roblox-mad-sound.mp3", "mad.mp3", "mad.wav"),
			"explosion": ("vine-boom.mp3", "explosion.mp3", "explosion.wav"),
		}
		self.effect_paths = {}
		for name, candidates in default_effect_files.items():
			path = next(
				(asset_dir / candidate for candidate in candidates if (asset_dir / candidate).is_file()),
				None,
			)
			self.effect_paths[name] = str(path) if path else None
		effect_files = {
			Path(path).resolve()
			for path in self.effect_paths.values()
			if path
		}
		self.meme_sound_paths = [
			path
			for pattern in ("*.mp3", "*.wav")
			for path in asset_dir.glob(pattern)
			if path.resolve() not in effect_files
			and path.resolve() != self.nyan_music_path.resolve()
		]
		self.effect_labels = {}
		self.current_mood = None
		self.desktop_x = 80
		self.desktop_y = 130
		self.desktop_dx = 2.0
		self.desktop_dy = 1.5
		self.animation_id = None
		self.finalizing = False

		self._build_ui()
		self._build_avatar()
		self._draw_cat()
		self._animate()
		self._update_mood()
		self.root.protocol("WM_DELETE_WINDOW", self._close_app)
		self._schedule_next_meme()
		if self.nyan_frames:
			self._schedule_next_nyan()
		if meme_load_errors:
			self.root.after_idle(
				lambda errors=tuple(meme_load_errors): messagebox.showwarning(
					"Some memes could not be loaded", "\n".join(errors)
				)
			)

	def _build_ui(self):
		header = tk.Frame(self.root, bg="#f2efe8", padx=24, pady=18)
		header.pack(fill="x")
		tk.Label(
			header,
			text="DESKTOP CAT",
			font=("TkDefaultFont", 20, "bold"),
			bg="#f2efe8",
			fg="#24211e",
		).pack(anchor="w")
		tk.Label(
			header,
			text="A tiny menace with a very dramatic exit.",
			font=("TkDefaultFont", 10),
			bg="#f2efe8",
			fg="#68615a",
		).pack(anchor="w", pady=(3, 0))

		self.scene = tk.Canvas(
			self.root,
			bg="#dce7df",
			highlightthickness=0,
			height=270,
		)
		self.scene.pack(fill="both", expand=True, padx=24)
		self.scene.bind("<Configure>", self._keep_cat_in_bounds)
		self.scene.bind("<Button-1>", self._pet_cat)

		controls = tk.Frame(self.root, bg="#f2efe8", padx=24, pady=16)
		controls.pack(fill="x")
		tk.Label(
			controls,
			text="IRRITATION",
			font=("TkDefaultFont", 9, "bold"),
			bg="#f2efe8",
			fg="#68615a",
		).grid(row=0, column=0, sticky="w")
		self.meter = ttk.Progressbar(
			controls, maximum=self.annoyance_limit, mode="determinate", length=220
		)
		self.meter.grid(row=1, column=0, sticky="ew", pady=(5, 0))
		self.status = tk.Label(
			controls,
			text="The cat is behaving. For now.",
			font=("TkDefaultFont", 10),
			bg="#f2efe8",
			fg="#24211e",
		)
		self.status.grid(row=0, column=1, rowspan=2, padx=16, sticky="w")

		settings = tk.Frame(self.root, bg="#f2efe8", padx=24)
		settings.pack(fill="x", pady=(0, 12))
		ttk.Checkbutton(
			settings,
			text="Desktop avatar",
			variable=self.avatar_visible,
			command=self._toggle_avatar,
		).grid(row=0, column=0, sticky="w")
		ttk.Checkbutton(
			settings,
			text="Cat prank enabled",
			variable=self.prank_enabled,
		).grid(row=0, column=1, sticky="w", padx=(10, 0))
		ttk.Checkbutton(
			settings,
			text="Simulate power-off scene",
			variable=self.simulate_shutdown,
		).grid(row=0, column=2, sticky="w", padx=(10, 0))
		ttk.Button(
			settings, text="Test finale", command=self._trigger_finale
		).grid(row=0, column=3, sticky="e", padx=(10, 0))

		effects = tk.LabelFrame(
			self.root,
			text="CAT SOUND EFFECTS (MP3 / WAV)",
			bg="#f2efe8",
			fg="#24211e",
			padx=8,
			pady=6,
		)
		effects.pack(fill="x", padx=24, pady=(0, 10))
		for column, name in enumerate(("happy", "irritated", "mad", "explosion")):
			group = tk.Frame(effects, bg="#f2efe8")
			group.grid(row=0, column=column, sticky="ew", padx=4)
			effects.grid_columnconfigure(column, weight=1)
			self.effect_labels[name] = tk.StringVar(
				value=f"{name.title()}: "
				+ (Path(self.effect_paths[name]).name if self.effect_paths[name] else "not set")
			)
			tk.Label(
				group,
				textvariable=self.effect_labels[name],
				bg="#f2efe8",
				fg="#68615a",
				anchor="w",
			).pack(fill="x")
			ttk.Button(
				group,
				text="Choose Audio",
				command=lambda sound=name: self._choose_effect(sound),
			).pack(fill="x", pady=(3, 2))
			ttk.Button(
				group,
				text=f"Play {name.title()}",
				command=lambda sound=name: self._play_effect(sound),
			).pack(fill="x")

		sounds = tk.LabelFrame(
			self.root,
			text="SOUND LIBRARY (MP3 / WAV)",
			bg="#f2efe8",
			fg="#24211e",
			padx=10,
			pady=8,
		)
		sounds.pack(fill="x", padx=24, pady=(0, 16))
		self.sound_list = tk.Listbox(sounds, height=3, exportselection=False)
		self.sound_list.pack(side="left", fill="x", expand=True)
		sound_buttons = tk.Frame(sounds, bg="#f2efe8")
		sound_buttons.pack(side="right", padx=(10, 0))
		ttk.Button(sound_buttons, text="Add Audio", command=self._add_sound).pack(fill="x")
		ttk.Button(sound_buttons, text="Play", command=self._play_sound).pack(fill="x", pady=4)
		ttk.Button(sound_buttons, text="Remove", command=self._remove_sound).pack(fill="x")

	def _build_avatar(self):
		self.avatar_window = tk.Toplevel(self.root)
		self.avatar_window.title("Desktop Cat Avatar")
		self.avatar_window.overrideredirect(True)
		self.avatar_window.attributes("-topmost", True)
		self.avatar_window.geometry(f"150x150+{self.desktop_x}+{self.desktop_y}")
		self.avatar_transparent_color = "#010203"
		self.avatar_shape_mood = None
		self.avatar_transparency_enabled = False
		if self.root.tk.call("tk", "windowingsystem") == "win32":
			self.avatar_window.attributes(
				"-transparentcolor", self.avatar_transparent_color
			)
			self.avatar_transparency_enabled = True
		self.avatar_canvas = tk.Canvas(
			self.avatar_window,
			width=150,
			height=150,
			bg=self.avatar_transparent_color,
			highlightthickness=0,
		)
		self.avatar_canvas.pack()
		self.avatar_canvas.bind("<Button-1>", self._avatar_click)
		self.avatar_canvas.bind("<ButtonPress-3>", self._start_avatar_drag)
		self.avatar_canvas.bind("<B3-Motion>", self._drag_avatar)
		self.avatar_images = {}
		asset_dir = Path(__file__).resolve().parent
		try:
			happy_image = tk.PhotoImage(file=str(asset_dir / "happy.png"))
			grumpy_image = tk.PhotoImage(file=str(asset_dir / "irritated.png"))
			self.avatar_images["happy"] = happy_image.subsample(4, 4)
			self.avatar_images["grumpy"] = grumpy_image.zoom(2, 2).subsample(4, 4)
		except tk.TclError:
			self.avatar_images.clear()
			self.avatar_canvas.configure(bg="#dce7df")
		self.avatar_window.withdraw()
		self._toggle_avatar()

	def _draw_avatar(self):
		self.avatar_canvas.delete("all")
		mood = "grumpy" if self.annoyance >= 30 else "happy"
		image_key = mood
		if image_key in self.avatar_images:
			image = self.avatar_images[image_key]
			width = max(150, image.width())
			height = max(150, image.height())
			self.avatar_canvas_size = (width, height)
			self.avatar_canvas.configure(width=width, height=height)
			self.avatar_window.geometry(
				f"{width}x{height}+{int(self.desktop_x)}+{int(self.desktop_y)}"
			)
			x = (width - image.width()) // 2
			y = (height - image.height()) // 2
			self.avatar_displayed_image = image
			self.avatar_canvas.create_image(x, y, image=image, anchor="nw")
			if not self.avatar_transparency_enabled and self.avatar_shape_mood != image_key:
				self.avatar_shape_mood = image_key
				self.root.after_idle(
					lambda current_key=image_key, current_image=image, left=x, top=y:
					self._apply_avatar_shape(current_key, current_image, left, top)
				)
		else:
			self.avatar_displayed_image = None
			self.avatar_canvas_size = (150, 150)
			self.avatar_canvas.configure(width=150, height=150)
			self.avatar_window.geometry(
				f"150x150+{int(self.desktop_x)}+{int(self.desktop_y)}"
			)
			self.avatar_canvas.create_oval(37, 46, 102, 111, fill="#e7894f", outline="#713f2b", width=2)
			self.avatar_canvas.create_polygon(43, 63, 46, 31, 65, 50, fill="#e7894f", outline="#713f2b", width=2)
			self.avatar_canvas.create_polygon(94, 63, 91, 31, 73, 50, fill="#e7894f", outline="#713f2b", width=2)
			self.avatar_canvas.create_oval(53, 65, 60, 73, fill="#24211e", outline="")
			self.avatar_canvas.create_oval(78, 65, 85, 73, fill="#24211e", outline="")
			self.avatar_canvas.create_polygon(66, 78, 73, 78, 69.5, 83, fill="#8b3c3c", outline="")
			self.avatar_canvas.create_arc(62, 80, 77, 94, start=200, extent=140, style="arc", outline="#713f2b")

	def _apply_avatar_shape(self, image_key, image, left, top):
		if self.avatar_displayed_image is not image:
			return
		if self.root.tk.call("tk", "windowingsystem") != "x11":
			self.avatar_canvas.configure(bg="#dce7df")
			self.avatar_transparency_enabled = True
			messagebox.showwarning(
				"Transparent avatar unavailable",
				"Transparent avatar backgrounds are not supported by this window system.",
			)
			return
		x11_path = ctypes.util.find_library("X11")
		xext_path = ctypes.util.find_library("Xext")
		if not x11_path or not xext_path:
			self._show_avatar_transparency_error(
				"X11 shape support is unavailable; cannot remove the avatar background."
			)
			return

		try:
			x11 = ctypes.CDLL(x11_path)
			xext = ctypes.CDLL(xext_path)
		except OSError as error:
			self._show_avatar_transparency_error(str(error))
			return
		x11.XOpenDisplay.argtypes = [ctypes.c_char_p]
		x11.XOpenDisplay.restype = ctypes.c_void_p
		x11.XCreateBitmapFromData.argtypes = [
			ctypes.c_void_p, ctypes.c_ulong, ctypes.c_char_p,
			ctypes.c_uint, ctypes.c_uint,
		]
		x11.XCreateBitmapFromData.restype = ctypes.c_ulong
		x11.XFreePixmap.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
		x11.XSync.argtypes = [ctypes.c_void_p, ctypes.c_int]
		x11.XCloseDisplay.argtypes = [ctypes.c_void_p]
		xext.XShapeQueryExtension.argtypes = [
			ctypes.c_void_p, ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int),
		]
		xext.XShapeCombineMask.argtypes = [
			ctypes.c_void_p, ctypes.c_ulong, ctypes.c_int, ctypes.c_int,
			ctypes.c_int, ctypes.c_ulong, ctypes.c_int,
		]

		display = x11.XOpenDisplay(None)
		if not display:
			self._show_avatar_transparency_error(
				"Could not open the X11 display to remove the avatar background."
			)
			return
		pixmap = None
		try:
			event_base = ctypes.c_int()
			error_base = ctypes.c_int()
			if not xext.XShapeQueryExtension(
				display, ctypes.byref(event_base), ctypes.byref(error_base)
			):
				self._show_avatar_transparency_error(
					"The X11 server does not support transparent shaped windows."
				)
				return

			width, height = self.avatar_canvas_size
			stride = (width + 7) // 8
			mask = bytearray(stride * height)
			for source_y in range(image.height()):
				for source_x in range(image.width()):
					if image.transparency_get(source_x, source_y):
						continue
					target_x = left + source_x
					target_y = top + source_y
					mask[target_y * stride + target_x // 8] |= 1 << (target_x % 8)

			pixmap = x11.XCreateBitmapFromData(
				display,
				self.avatar_window.winfo_id(),
				ctypes.c_char_p(bytes(mask)),
				width,
				height,
			)
			if not pixmap:
				self._show_avatar_transparency_error(
					"Could not create the transparent avatar mask."
				)
				return
			xext.XShapeCombineMask(
				display,
				self.avatar_window.winfo_id(),
				0,
				0,
				0,
				pixmap,
				0,
			)
			x11.XSync(display, 0)
		finally:
			if pixmap:
				x11.XFreePixmap(display, pixmap)
			x11.XCloseDisplay(display)
		self.avatar_shape_mood = image_key

	def _show_avatar_transparency_error(self, error):
		self.avatar_canvas.configure(bg="#dce7df")
		self.avatar_transparency_enabled = True
		messagebox.showerror("Transparent avatar unavailable", error)

	def _close_app(self):
		self.root.destroy()

	def _photo_from_image(self, image):
		buffer = io.BytesIO()
		image.save(buffer, format="PNG")
		encoded_image = base64.b64encode(buffer.getvalue())
		return tk.PhotoImage(data=encoded_image, format="png", master=self.root)

	def _schedule_next_meme(self):
		self.root.after(random.randint(1800, 5500), self._show_random_meme)

	def _show_random_meme(self):
		if (
			self.meme_images
			and self.prank_enabled.get()
			and not self.finalizing
			and not self.shutdown_window
		):
			if len(self.meme_windows) < 4:
				image_index = random.randrange(len(self.meme_images))
				image = self.meme_images[image_index]
				popup = tk.Toplevel(self.root)
				popup.overrideredirect(True)
				popup.attributes("-topmost", True)
				width, height = image.width(), image.height()
				max_x = max(0, self.root.winfo_screenwidth() - width)
				max_y = max(0, self.root.winfo_screenheight() - height)
				x = random.randint(0, max_x)
				y = random.randint(0, max_y)
				popup.geometry(f"{width}x{height}+{x}+{y}")
				label = tk.Label(popup, image=image, borderwidth=0)
				label.pack()
				dismiss = lambda _event, window=popup: self._dismiss_meme(window)
				self.meme_windows[popup] = {
					"image": image,
					"x": x,
					"y": y,
					"dx": random.choice((-1, 1)) * random.uniform(2.0, 5.0),
					"vy": random.uniform(-2.0, 2.0),
					"width": width,
					"height": height,
				}
				label.bind("<Button-1>", dismiss)
				popup.bind("<Button-1>", dismiss)
		self._schedule_next_meme()

	def _schedule_next_nyan(self):
		self.root.after(random.randint(12000, 24000), self._start_nyan_flight)

	def _start_nyan_flight(self):
		if (
			self.nyan_frames
			and not self.nyan_window
			and self.prank_enabled.get()
			and not self.finalizing
			and not self.shutdown_window
		):
			self.nyan_frame_index = 0
			self.nyan_frame_ticks = 0
			self.nyan_window = tk.Toplevel(self.root)
			self.nyan_window.overrideredirect(True)
			self.nyan_window.attributes("-topmost", True)
			self.nyan_label = tk.Label(
				self.nyan_window,
				image=self.nyan_frames[0],
				borderwidth=0,
				highlightthickness=0,
			)
			self.nyan_label.pack()
			self.nyan_label.bind("<Button-1>", self._play_nyan_music)
			self.nyan_window.bind("<Button-1>", self._play_nyan_music)
			width = self.nyan_frames[0].width()
			height = self.nyan_frames[0].height()
			self.nyan_x = -width
			max_y = max(0, self.root.winfo_screenheight() - height)
			self.nyan_y = random.randint(0, max_y)
			self.nyan_window.geometry(
				f"{width}x{height}{self.nyan_x:+d}{self.nyan_y:+d}"
			)
			self.nyan_speed = random.randint(9, 15)
		self._schedule_next_nyan()

	def _play_nyan_music(self, _event=None):
		if self.nyan_music_path.is_file():
			self._play_audio(str(self.nyan_music_path))
		else:
			messagebox.showerror(
				"Nyan Cat music not found",
				f"Could not find the music file: {self.nyan_music_path.name}",
			)

	def _animate_nyan(self):
		if not self.nyan_window:
			return
		if not self.nyan_window.winfo_exists():
			self.nyan_window = None
			self.nyan_label = None
			return
		if self.shutdown_window or self.finalizing or not self.prank_enabled.get():
			self.nyan_window.withdraw()
			return
		self.nyan_window.deiconify()
		self.nyan_x += self.nyan_speed
		self.nyan_frame_ticks += 1
		if self.nyan_frame_ticks >= 3:
			self.nyan_frame_ticks = 0
			self.nyan_frame_index = (self.nyan_frame_index + 1) % len(self.nyan_frames)
			self.nyan_label.configure(image=self.nyan_frames[self.nyan_frame_index])
		self.nyan_window.geometry(f"{self.nyan_x:+d}{self.nyan_y:+d}")
		if self.nyan_x > self.root.winfo_screenwidth():
			self.nyan_window.destroy()
			self.nyan_window = None
			self.nyan_label = None

	def _animate_meme_windows(self):
		screen_width = self.root.winfo_screenwidth()
		screen_height = self.root.winfo_screenheight()
		for popup, motion in tuple(self.meme_windows.items()):
			if not popup.winfo_exists():
				self.meme_windows.pop(popup, None)
				continue
			motion["x"] += motion["dx"]
			motion["vy"] += 0.35
			motion["y"] += motion["vy"]
			max_x = max(0, screen_width - motion["width"])
			max_y = max(0, screen_height - motion["height"])
			if motion["x"] <= 0 or motion["x"] >= max_x:
				motion["dx"] *= -1
				motion["x"] = min(max(motion["x"], 0), max_x)
			if motion["y"] <= 0:
				motion["y"] = min(max(motion["y"], 0), max_y)
				motion["vy"] = max(abs(motion["vy"]) * 0.9, 3.0)
			elif motion["y"] >= max_y:
				motion["y"] = max_y
				motion["vy"] = -max(abs(motion["vy"]) * 0.9, 5.0)
			popup.geometry(f"+{int(motion['x'])}+{int(motion['y'])}")

	def _dismiss_meme(self, popup):
		if popup in self.meme_windows:
			del self.meme_windows[popup]
			popup.destroy()
			if self.meme_sound_paths:
				self._play_audio(str(random.choice(self.meme_sound_paths)))

	def _toggle_avatar(self):
		if self.avatar_visible.get():
			self.avatar_window.deiconify()
			self.avatar_window.lift()
			self.avatar_window.attributes("-topmost", True)
			self._draw_avatar()
		else:
			self.avatar_window.withdraw()

	def _start_avatar_drag(self, event):
		self.drag_offset_x = event.x_root - self.desktop_x
		self.drag_offset_y = event.y_root - self.desktop_y

	def _drag_avatar(self, event):
		self.desktop_x = event.x_root - self.drag_offset_x
		self.desktop_y = event.y_root - self.drag_offset_y
		self.avatar_window.geometry(f"+{self.desktop_x}+{self.desktop_y}")

	def _avatar_click(self, event):
		self._pet_cat(event)
		self._play_sound(show_errors=False)

	def _add_sound(self):
		path = filedialog.askopenfilename(
			title="Add an audio file",
			filetypes=[
				("Audio files", "*.mp3 *.wav"),
				("MP3 audio", "*.mp3"),
				("WAV audio", "*.wav"),
				("All files", "*.*"),
			],
		)
		if path:
			self.sound_paths.append(path)
			self.sound_list.insert("end", path.rsplit("/", 1)[-1])
			self.sound_list.selection_clear(0, "end")
			self.sound_list.selection_set("end")

	def _choose_effect(self, sound_name):
		path = filedialog.askopenfilename(
			title=f"Choose the {sound_name} sound",
			filetypes=[
				("MP3 audio", "*.mp3"),
				("WAV audio", "*.wav"),
				("All files", "*.*"),
			],
		)
		if path:
			self.effect_paths[sound_name] = path
			self.effect_labels[sound_name].set(f"{sound_name.title()}: {Path(path).name}")

	def _play_effect(self, sound_name):
		path = self.effect_paths[sound_name]
		if not path or not Path(path).is_file():
			messagebox.showerror(
				"Sound not set",
				f"Choose an audio file for {sound_name} before playing it.",
			)
			return
		self._play_audio(path)

	def _play_audio(self, path, show_errors=True):
		if pygame is None:
			if show_errors:
				messagebox.showerror(
					"Audio unavailable",
					"Install the audio dependency with: pip install -r requirements.txt",
				)
			return False
		try:
			if not pygame.mixer.get_init():
				pygame.mixer.init()
			pygame.mixer.music.load(path)
			pygame.mixer.music.play()
		except Exception as error:
			if show_errors:
				messagebox.showerror("Could not play audio", str(error))
			return False
		return True

	def _play_sound(self, show_errors=True):
		selection = self.sound_list.curselection()
		if not selection:
			return
		self._play_audio(self.sound_paths[selection[0]], show_errors)

	def _remove_sound(self):
		selection = self.sound_list.curselection()
		if selection:
			index = selection[0]
			self.sound_list.delete(index)
			del self.sound_paths[index]

	def _draw_cat(self):
		self.scene.delete("cat")
		x, y = self.cat_x, self.cat_y
		self.scene.create_oval(
			x - 34, y - 28, x + 34, y + 34,
			fill="#e7894f", outline="#713f2b", width=2, tags="cat"
		)
		self.scene.create_polygon(
			x - 27, y - 13, x - 25, y - 48, x - 4, y - 27,
			fill="#e7894f", outline="#713f2b", width=2, tags="cat"
		)
		self.scene.create_polygon(
			x + 27, y - 13, x + 25, y - 48, x + 4, y - 27,
			fill="#e7894f", outline="#713f2b", width=2, tags="cat"
		)
		self.scene.create_oval(x - 16, y - 6, x - 8, y + 3, fill="#24211e", tags="cat")
		self.scene.create_oval(x + 8, y - 6, x + 16, y + 3, fill="#24211e", tags="cat")
		self.scene.create_polygon(
			x - 4, y + 8, x + 4, y + 8, x, y + 13,
			fill="#8b3c3c", outline="", tags="cat"
		)
		self.scene.create_arc(
			x - 9, y + 10, x + 9, y + 24,
			start=200, extent=140, style="arc", outline="#713f2b", tags="cat"
		)
		self.scene.create_line(x - 15, y + 12, x - 40, y + 7, fill="#713f2b", tags="cat")
		self.scene.create_line(x + 15, y + 12, x + 40, y + 7, fill="#713f2b", tags="cat")
		self.scene.create_text(
			x, y + 54, text="click to annoy", fill="#4d574f",
			font=("TkDefaultFont", 9), tags="cat"
		)

	def _keep_cat_in_bounds(self, event):
		self.cat_x = min(max(self.cat_x, 50), max(50, event.width - 50))
		self.cat_y = min(max(self.cat_y, 60), max(60, event.height - 70))
		self._draw_cat()

	def _animate(self):
		self._animate_nyan()
		if not self.shutdown_window and not self.finalizing:
			self._animate_meme_windows()
		if self.prank_enabled.get() and not self.shutdown_window and not self.finalizing:
			width = max(self.scene.winfo_width(), 100)
			height = max(self.scene.winfo_height(), 100)
			self.cat_x += self.dx
			self.cat_y += self.dy
			if self.cat_x < 48 or self.cat_x > width - 48:
				self.dx *= -1
				self.cat_x = min(max(self.cat_x, 48), width - 48)
				self._bump_annoyance(1)
			if self.cat_y < 55 or self.cat_y > height - 65:
				self.dy *= -1
				self.cat_y = min(max(self.cat_y, 55), height - 65)
			self._draw_cat()
			if random.random() < 0.012:
				self.status.configure(text=random.choice([
					"The cat is judging your posture.",
					"A suspicious paw is approaching.",
					"The cat has knocked nothing over. Yet.",
				]))
				self._bump_annoyance(2)
			self._animate_desktop_avatar()
		self.animation_id = self.root.after(40, self._animate)

	def _animate_desktop_avatar(self):
		if not self.avatar_visible.get():
			return
		screen_width = self.root.winfo_screenwidth()
		screen_height = self.root.winfo_screenheight()
		avatar_width, avatar_height = self.avatar_canvas_size
		self.desktop_x += self.desktop_dx
		self.desktop_y += self.desktop_dy
		if self.desktop_x < 0 or self.desktop_x > screen_width - avatar_width:
			self.desktop_dx *= -1
			self.desktop_x = min(max(self.desktop_x, 0), screen_width - avatar_width)
		if self.desktop_y < 0 or self.desktop_y > screen_height - avatar_height:
			self.desktop_dy *= -1
			self.desktop_y = min(max(self.desktop_y, 0), screen_height - avatar_height)
		self.avatar_window.geometry(f"+{int(self.desktop_x)}+{int(self.desktop_y)}")
		self._draw_avatar()

	def _pet_cat(self, _event):
		if self.prank_enabled.get():
			self._bump_annoyance(8)
			self.status.configure(text="The cat accepts your attention, then demands more.")

	def _bump_annoyance(self, amount):
		self.annoyance = min(self.annoyance + amount, self.annoyance_limit)
		self.meter.configure(value=self.annoyance)
		self._update_mood()
		if self.annoyance >= self.annoyance_limit:
			self._trigger_finale()

	def _update_mood(self, play=True):
		if self.annoyance >= 60:
			mood = "mad"
		elif self.annoyance >= 30:
			mood = "irritated"
		else:
			mood = "happy"
		if mood == self.current_mood:
			return
		self.current_mood = mood
		if play:
			self._play_effect(mood)

	def _trigger_finale(self):
		if self.shutdown_window or self.finalizing:
			return
		self.finalizing = True
		self.annoyance = 0
		self._update_mood(play=False)
		self.meter.configure(value=0)
		self.status.configure(text="The cat has had enough.")
		self.scene.delete("cat")
		for angle in range(0, 360, 45):
			radians = math.radians(angle)
			start_x = self.cat_x + 12 * math.cos(radians)
			start_y = self.cat_y + 12 * math.sin(radians)
			end_x = self.cat_x + 65 * math.cos(radians)
			end_y = self.cat_y + 65 * math.sin(radians)
			self.scene.create_line(
				start_x, start_y, end_x, end_y,
				fill=random.choice(("#e7894f", "#f4c95d", "#d95b43")),
				width=5,
				tags="finale",
			)
		self.scene.create_text(
			self.cat_x,
			self.cat_y,
			text="POOF!",
			fill="#713f2b",
			font=("TkDefaultFont", 18, "bold"),
			tags="finale",
		)
		self.root.after(550, self._finish_explosion)

	def _finish_explosion(self):
		self.scene.delete("finale")
		if self.simulate_shutdown.get():
			self.root.after(150, self._show_fake_shutdown)
		else:
			self.finalizing = False
			self._draw_cat()
			self._draw_avatar()
			self.status.configure(text="Finale test complete. No power-off scene was shown.")

	def _show_fake_shutdown(self):
		if self.shutdown_window:
			return
		self.shutdown_window = tk.Toplevel(self.root)
		screen = self.shutdown_window
		screen.configure(bg="#050607")
		screen.attributes("-fullscreen", True)
		screen.attributes("-topmost", True)
		screen.bind("<Escape>", self._close_fake_shutdown)
		screen.bind("<Button-1>", self._close_fake_shutdown)
		screen.bind("<Key>", self._close_fake_shutdown)
		tk.Label(screen, text="", bg="#050607").pack(expand=True)
		self._play_effect("explosion")
		screen.after(1000, self._show_shutdown_message)

	def _show_shutdown_message(self):
		if self.shutdown_window and self.shutdown_window.winfo_exists():
			tk.Label(
				self.shutdown_window,
				text="The cat has dramatically powered off... nothing.\n\nPress Esc or click to return.",
				font=("TkDefaultFont", 16),
				fg="#d9dfda",
				bg="#050607",
				justify="center",
			).place(relx=0.5, rely=0.5, anchor="center")

	def _close_fake_shutdown(self, _event=None):
		if self.shutdown_window:
			self.shutdown_window.destroy()
			self.shutdown_window = None
			self.finalizing = False
			self.annoyance = 0
			self.meter.configure(value=0)
			self._update_mood(play=False)
			self._draw_cat()
			self._draw_avatar()
			self.status.configure(text="Back online. The cat looks pleased with itself.")


def main():
	root = tk.Tk()
	DesktopCat(root)
	root.after(0, root.iconify)
	root.mainloop()


if __name__ == "__main__":
	main()
