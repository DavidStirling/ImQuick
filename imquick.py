# ImQuick - A lightweight scientific image viewer.
# Copyright(C) 2021 David Stirling
# Canvas pan/zoom code adapted from https://stackoverflow.com/questions/41656176/tkinter-canvas-zoom-move-pan
# Drag/drop utilises the tkdnd2 extension https://github.com/petasis/tkdnd
# and wrapper https://sourceforge.net/projects/tkinterdnd/

import math
import imageio
import os
import re
import sys
import numpy as np
from PIL import Image, ImageTk
import tkinter as tk
import tkinter.ttk as ttk
import tkinter.filedialog as tkfiledialog
import tkinterdnd2 as tkDnD

__version__ = "1.0.1"

SUPPORTED_EXTENSIONS = {".tif", ".tiff", ".gif", ".png", ".jpeg", ".jpg", ".bmp", ".npz", ".itk"}
if sys.platform == "win32":
    ICON_FILE = 'ImQuick.ico'
else:
    ICON_FILE = 'ImQuick.png'
INTERP_DEFS = {'Nearest': Image.NEAREST, 'Bilinear': Image.BILINEAR,
               'Bicubic': Image.BICUBIC, 'Lanczos': Image.ANTIALIAS}


def not_without_file(func):
    # Decorator to only run a function when a file is already loaded. Arg 0 = self.
    def wrapper(*args, **kwargs):
        if args[0].file:
            func(*args, **kwargs)
    return wrapper


class HideyScrollBar(ttk.Scrollbar):
    # Scrollbars which auto-hide when not needed.
    def set(self, mini, maxi):
        if float(mini) <= 0.0 and float(maxi) >= 1.0:
            self.grid_remove()
        else:
            self.grid()
            ttk.Scrollbar.set(self, mini, maxi)


class ImQuick(tk.Toplevel):
    # Main GUI window
    def __init__(self, master, filename=r""):
        super(ImQuick, self).__init__()
        self.master = master
        self.title(f"ImQuick {__version__}")
        self.geometry(f"500x500")
        self.file = None
        self.file_list = []
        self.current_index = 0
        self.image_data = None
        self.scaled_image_data = None
        self.displayed_image = None
        self.display = None
        self.zoom_factor = 1
        self.delta = 1.3
        self.width = 0
        self.height = 0
        self.container = None
        self.info_popup = None
        self.display_popup = None
        self.about_popup = None

        self.reader = None
        self.max_plane = 0
        self.displayed_plane = 0

        self.min_display_value = tk.IntVar(self, value=0)
        self.max_display_value = tk.IntVar(self, value=255)
        self.per_channel_contrast = False
        self.display_values_array = [0, 255]
        self.z_display_value = tk.IntVar(self, value=0)
        self.interp_mode = tk.StringVar(self, value='Nearest')

        self.min_display_value.trace("w", self.update_min_display)
        self.max_display_value.trace("w", self.update_max_display)

        self.menubar = self.create_menus()

        self.config(menu=self.menubar)

        self.image_frame = ttk.Frame(self)
        self.canvas = tk.Canvas(self.image_frame)
        h = HideyScrollBar(self.image_frame, orient=tk.HORIZONTAL)
        v = HideyScrollBar(self.image_frame, orient=tk.VERTICAL)
        v.configure(command=self.scroll_y)  # bind scrollbars to the canvas
        h.configure(command=self.scroll_x)
        self.canvas.config(xscrollcommand=h.set, yscrollcommand=v.set)

        self.bind('a', self.auto_contrast)
        self.bind('<Left>', self.prev_file)
        self.bind('<Right>', self.next_file)
        self.canvas.bind("<Motion>", self.hover_pixel)
        self.bind("<Motion>", self.no_pixel)

        self.canvas.bind('<Configure>', self.resize_window)  # canvas is resized
        self.canvas.bind('<ButtonPress-1>', self.move_from)
        self.canvas.bind('<B1-Motion>', self.move_to)
        self.canvas.bind('<MouseWheel>', self.zoom_mouse)
        self.protocol('WM_DELETE_WINDOW', self.close)

        # PyCharm will complain, but these binds are needed for drag and drop.
        self.drop_target_register(tkDnD.DND_FILES)
        self.dnd_bind('<<Drop>>', self.on_drop)

        self.xyvalue = tk.StringVar(value="-")
        self.pixelvalue = tk.StringVar(value="-")

        self.statusbar = ttk.Frame(self, borderwidth=1)

        self.open_button = ttk.Button(self.statusbar, style='mini.TButton', text="O", command=self.open_file)
        self.prev_button = ttk.Button(self.statusbar, style='mini.TButton', text="<", command=self.prev_file)
        self.next_button = ttk.Button(self.statusbar, style='mini.TButton', text=">", command=self.next_file)

        self.zoomout_button = ttk.Button(self.statusbar, style='mini.TButton', text="-", command=self.zoom_out)
        self.zoomin_button = ttk.Button(self.statusbar, style='mini.TButton', text="+", command=self.zoom_in)

        self.zoomfull_button = ttk.Button(self.statusbar, style='mini.TButton', text="r", command=self.first_show_image)
        self.zoomfit_button = ttk.Button(self.statusbar, style='mini.TButton', text="f", command=self.fit_to_window)

        self.autocontrast_button = ttk.Button(self.statusbar, style='mini.TButton', text="", command=self.auto_contrast)
        self.contrast_button = ttk.Button(self.statusbar, style='mini.TButton', text="c", command=self.adjust_contrast)

        self.open_icon = tk.PhotoImage(file=resource_directory("OpenFile.png"))
        self.zoomin_icon = tk.PhotoImage(file=resource_directory("Plus.png"))
        self.zoomout_icon = tk.PhotoImage(file=resource_directory("Minus.png"))
        self.next_icon = tk.PhotoImage(file=resource_directory("Right.png"))
        self.prev_icon = tk.PhotoImage(file=resource_directory("Left.png"))
        self.full_icon = tk.PhotoImage(file=resource_directory("ActualSize.png"))
        self.fit_icon = tk.PhotoImage(file=resource_directory("FitWindow.png"))
        self.contrast_icon = tk.PhotoImage(file=resource_directory("Brightness.png"))
        self.autocontrast_icon = tk.PhotoImage(file=resource_directory("BrightnessAuto.png"))

        self.open_button.config(image=self.open_icon)
        self.zoomin_button.config(image=self.zoomin_icon)
        self.zoomout_button.config(image=self.zoomout_icon)
        self.next_button.config(image=self.next_icon)
        self.prev_button.config(image=self.prev_icon)
        self.zoomfull_button.config(image=self.full_icon)
        self.zoomfit_button.config(image=self.fit_icon)
        self.contrast_button.config(image=self.contrast_icon)
        self.autocontrast_button.config(image=self.autocontrast_icon)

        self.statusseparator = ttk.Separator(self.statusbar, orient='vertical')

        self.status_xy = ttk.Label(self.statusbar, textvariable=self.xyvalue, width=15, anchor=tk.CENTER)
        self.status_pixel = ttk.Label(self.statusbar, textvariable=self.pixelvalue, width=20, anchor=tk.CENTER)

        self.stack_ctrl = tk.Frame(master=self.image_frame, relief=tk.GROOVE, borderwidth=2)
        self.z_slider = ttk.Scale(self.stack_ctrl,
                                  variable=self.z_display_value,
                                  from_=0,
                                  to=self.max_plane,
                                  command=lambda x: self.set_z_plane(round(float(x))))
        validate = self.register(self.set_z_plane)
        self.z_label = ttk.Entry(self.stack_ctrl,
                                 textvariable=self.z_display_value,
                                 validate='key',
                                 validatecommand=(validate, '%P'),
                                 width=5,
                                 justify=tk.CENTER,
                                 )

        self.z_slider.pack(side=tk.LEFT, padx=10, fill=tk.X, expand=True)
        self.z_label.pack(side=tk.LEFT, padx=5)

        self.open_button.pack(side=tk.LEFT, padx=(3, 0))
        self.prev_button.pack(side=tk.LEFT, padx=(3, 0))
        self.next_button.pack(side=tk.LEFT, padx=(0, 3))
        self.zoomout_button.pack(side=tk.LEFT, padx=(3, 0))
        self.zoomin_button.pack(side=tk.LEFT, padx=(0, 3))
        self.zoomfull_button.pack(side=tk.LEFT, padx=(3, 3))
        self.zoomfit_button.pack(side=tk.LEFT, padx=(3, 3))
        self.contrast_button.pack(side=tk.LEFT, padx=(3, 0))
        self.autocontrast_button.pack(side=tk.LEFT, padx=(0, 3))

        self.status_pixel.pack(side=tk.RIGHT, fill=tk.X)
        self.statusseparator.pack(side=tk.RIGHT, fill=tk.BOTH)
        self.status_xy.pack(side=tk.RIGHT, fill=tk.X)

        self.statusbar.pack(fill=tk.X)
        self.image_frame.pack(fill=tk.BOTH, expand=True)

        self.image_frame.rowconfigure(0, weight=1)
        self.image_frame.columnconfigure(0, weight=1)
        v.grid(row=0, column=1, sticky='ns')
        h.grid(row=1, column=0, sticky='we')
        self.canvas.grid(row=0, column=0, sticky='nswe')

        self.canvas.update()

        if filename:
            self.load_image(filename)
        else:
            self.canvas.create_text(self.canvas.winfo_width() // 2, self.canvas.winfo_height() // 2,
                                    anchor=tk.CENTER, text="[Drag a file here to open]")
        if self.max_plane > 0:
            self.stack_ctrl.grid(row=2, column=0, columnspan=2, sticky='ew')

    def on_drop(self, event):
        # Open files dropped onto the window
        line = event.data
        to_open = []
        for obj in re.findall('{.*?}', line):
            to_open.append(obj[1:-1])
            line = line.replace(obj, "")
        to_open += line.split(" ")
        for file in to_open:
            if os.path.splitext(file)[-1].lower() in SUPPORTED_EXTENSIONS:
                if self.file:
                    ImQuick(self.master, file)
                else:
                    self.load_image(file)

    def create_menus(self):
        # Create the menu bar.
        menubar = tk.Menu(self)
        menu_file = tk.Menu(menubar, tearoff=False)
        menu_view = tk.Menu(menubar, tearoff=False)
        menu_help = tk.Menu(menubar, tearoff=False)

        menu_file.add_command(label='Open Image', command=self.open_file)
        menu_file.add_separator()
        menu_file.add_command(label='Previous Image', command=self.prev_file)
        menu_file.add_command(label='Next Image', command=self.next_file)
        menu_file.add_separator()
        menu_file.add_command(label='Close', command=self.close)

        menu_view.add_command(label='Show information', command=self.get_info)
        menu_view.add_command(label='Adjust brightness', command=self.adjust_contrast)

        menu_help.add_command(label='Documentation', command=docs)
        menu_help.add_command(label='About ImQuick', command=self.about)

        interp_submenu = tk.Menu(menubar, tearoff=False)
        interp_submenu.add_radiobutton(label="Nearest", variable=self.interp_mode, command=self.show_image)
        interp_submenu.add_radiobutton(label="Bilinear", variable=self.interp_mode, command=self.show_image)
        interp_submenu.add_radiobutton(label="Bicubic", variable=self.interp_mode, command=self.show_image)
        interp_submenu.add_radiobutton(label="Lanczos", variable=self.interp_mode, command=self.show_image)
        menu_view.add_cascade(label='Interpolation mode', menu=interp_submenu, underline=0)

        menubar.add_cascade(menu=menu_file, label='File')
        menubar.add_cascade(menu=menu_view, label='View')
        menubar.add_cascade(menu=menu_help, label='Help')
        return menubar

    def update_min_display(self, *args):
        # Set minimum displayed pixel intensity
        min_d = self.min_display_value.get()
        max_d = self.max_display_value.get()
        dirty = False
        if min_d == 255:
            self.min_display_value.set(254)
        if min_d >= max_d:
            self.max_display_value.set(min_d + 1)
            dirty = True
        if self.display_popup and not self.display_popup.working:
            offset = self.display_popup.offset
            self.display_values_array[offset] = self.min_display_value.get()
            self.display_values_array[offset + 1] = self.max_display_value.get()
        if not dirty:
            self.update_contrast()

    def update_max_display(self,  *args):
        # Set maximum displayed pixel intensity
        min_d = self.min_display_value.get()
        max_d = self.max_display_value.get()
        dirty = False
        if max_d == 0:
            self.max_display_value.set(1)
        if min_d >= max_d:
            self.min_display_value.set(max_d - 1)
            dirty = True
        if self.display_popup and not self.display_popup.working:
            offset = self.display_popup.offset
            self.display_values_array[offset] = self.min_display_value.get()
            self.display_values_array[offset + 1] = self.max_display_value.get()
        if not dirty:
            self.update_contrast()

    @not_without_file
    def update_z_display(self, *args):
        if self.max_plane == 0 or self.displayed_plane == self.z_display_value.get():
            return
        else:
            self.displayed_plane = self.z_display_value.get()
            self.image_data = self.reader.get_data(self.displayed_plane)
            self.scaled_image_data = rescale_data(self.image_data)
            self.update_contrast()

    def set_z_plane(self, val):
        try:
            if val == '':
                val = 0
            else:
                val = int(val)
            if val > self.max_plane:
                self.z_display_value.set(self.max_plane)
            elif val < 0:
                self.z_display_value.set(0)
            else:
                self.z_display_value.set(val)
            self.update_z_display()
            return True
        except ValueError:
            return False

    def update_contrast(self, *args):
        # Apply pixel min/max intensity display
        temp_data = self.scaled_image_data.copy()
        if self.per_channel_contrast:
            min_max = self.display_values_array[2:].copy()
            channels_pool = []
            for i in range(temp_data.shape[-1]):
                channel_data = temp_data[:, :, i]
                new_min = min_max.pop(0)
                new_max = min_max.pop(0)
                channel_data[channel_data < new_min] = new_min
                channel_data = ((channel_data - new_min) / (new_max - new_min))
                channels_pool.append(channel_data)
            temp_data = np.dstack(channels_pool)
        else:
            new_min = self.min_display_value.get()
            new_max = self.max_display_value.get()
            temp_data[temp_data < new_min] = new_min
            temp_data = ((temp_data - new_min) / (new_max - new_min))
        temp_data[temp_data > 1] = 1
        self.displayed_image = Image.fromarray((temp_data * 255).astype('uint8'))
        self.show_image()

    def about(self):
        # Show 'about' dialog
        if self.about_popup:
            self.about_popup.lift()
        else:
            self.about_popup = AboutPopup(self)

    @not_without_file
    def get_info(self):
        # Show image information dialog
        if self.info_popup:
            self.info_popup.lift()
        else:
            self.info_popup = InfoPopup(self, self.image_data, self.file)

    @not_without_file
    def adjust_contrast(self):
        # Show contrast adjustment dialog
        if self.display_popup:
            self.display_popup.lift()
        else:
            self.display_popup = DisplayPopup(self, self.file, self.image_data.shape)

    @not_without_file
    def auto_contrast(self, event=None):
        # Set contrast range to min-max pixel intensity values.
        self.min_display_value.set(self.scaled_image_data.min())
        self.max_display_value.set(self.scaled_image_data.max())
        self.update_contrast()

    def load_image(self, file):
        # Open an image
        self.canvas.delete("all")
        self.focus_set()
        file = os.path.normpath(file)
        try:
            self.reader = imageio.get_reader(file)
            if os.path.splitext(file)[-1].lower() in ('.tif', '.tiff'):
                # Use the Pillow reader if the file is compressed.
                meta = self.reader.get_meta_data()
                if meta.get('compression', False) == 5:  # LZW compression
                    self.reader = imageio.get_reader(file, format='TIFF-PIL')
            self.max_plane = self.reader.get_length() - 1
            if self.max_plane > 0:
                self.image_data = self.reader.get_data(self.max_plane // 2)
                self.z_slider.config(to=self.max_plane)
                self.z_display_value.set(self.max_plane // 2)
                self.stack_ctrl.grid(row=2, column=0, columnspan=2, sticky='ew')
            else:
                self.image_data = self.reader.get_data(0)
                self.stack_ctrl.grid_remove()
                self.update()
        except:
            self.canvas.create_text(self.canvas.winfo_width() // 2, self.canvas.winfo_height() // 2,
                                    anchor=tk.CENTER, text="[Unable to open file]")
            self.reader = None
            self.file = None
            return
        if self.min_display_value.get() != 0:
            self.min_display_value.set(0)
        if self.max_display_value.get() != 255:
            self.max_display_value.set(255)
        if len(self.image_data.shape) < 3:
            self.display_values_array = [0, 255]
        else:
            self.display_values_array = [0, 255] * (self.image_data.shape[-1] + 1)
        self.scaled_image_data = rescale_data(self.image_data)
        self.displayed_image = Image.fromarray(self.scaled_image_data)
        self.width, self.height = self.displayed_image.size
        self.file = file
        if self.info_popup is not None:
            self.info_popup.show_info(self.image_data, file)
        if self.display_popup is not None:
            self.display_popup.switch_image(file, self.image_data.shape)
        self.first_show_image(loading=True)
        self.title(f"ImQuick {__version__} - {'...' + file[-100:] if len(file) > 100 else file}")
        if self.info_popup:
            self.info_popup.show_info(self.image_data, file)

    @not_without_file
    def scroll_y(self, *args):
        # Scroll the canvas in the y axis
        self.canvas.yview(*args)
        self.show_image()

    @not_without_file
    def scroll_x(self, *args):
        # Scroll the canvas in the x axis
        self.canvas.xview(*args)
        self.show_image()

    @not_without_file
    def move_from(self, event):
        # Set starting position for mouse drag
        self.canvas.scan_mark(event.x, event.y)

    @not_without_file
    def move_to(self, event):
        # Move canvas to target position when dragging
        self.canvas.scan_dragto(event.x, event.y, gain=1)
        self.show_image()

    @not_without_file
    def zoom_in(self):
        # Zoom in, towards the center of the canvas
        i = min(self.canvas.winfo_width(), self.canvas.winfo_height())
        if i/5 < self.zoom_factor:
            return
        self.zoom_factor *= self.delta
        scale = self.delta
        self.zoom_image(self.canvas.winfo_width() / 2, self.canvas.winfo_height() / 2, scale)

    @not_without_file
    def zoom_out(self):
        # Zoom in, from the center of the canvas
        i = min(self.width, self.height)
        if int(i * self.zoom_factor) < 30:
            return
        self.zoom_factor /= self.delta
        scale = 1 / self.delta
        self.zoom_image(self.canvas.winfo_width() / 2, self.canvas.winfo_height() / 2, scale)

    @not_without_file
    def zoom_mouse(self, event):
        # Zoom relative to the mouse cursor
        x = self.canvas.canvasx(event.x)
        y = self.canvas.canvasy(event.y)
        bbox = self.canvas.bbox(self.container)
        if not bbox[0] < x < bbox[2] or not bbox[1] < y < bbox[3]:
            return
        scale = 1.0
        if event.delta < 0:
            i = min(self.width, self.height)
            if int(i * self.zoom_factor) < 30:
                return
            self.zoom_factor /= self.delta
            scale = 1 / self.delta
        if event.delta > 0:
            i = min(self.canvas.winfo_width(), self.canvas.winfo_height())
            if i/5 < self.zoom_factor:
                return
            self.zoom_factor *= self.delta
            scale = self.delta
        self.zoom_image(x, y, scale)

    @not_without_file
    def zoom_image(self, x, y, scale):
        # Apply a zoom transform
        self.zoomfit_button.state(['!pressed'])
        self.canvas.scale(self.container, x, y, scale, scale)  # Resize the bounding box too
        self.show_image()

    @not_without_file
    def first_show_image(self, event=None, loading=False):
        # Setup display of an image for the first time, (or reset pan/zoom).
        init_x = (self.canvas.winfo_width() // 2) - (self.width // 2)
        init_y = (self.canvas.winfo_height() // 2) - (self.height // 2)
        if loading and (self.width > self.canvas.winfo_width() or self.height > self.canvas.winfo_height()):
            self.fit_to_window()
        else:
            self.zoomfit_button.state(['!pressed'])
            self.zoom_factor = 1
            self.container = self.canvas.create_rectangle(init_x, init_y, init_x + self.width, init_y + self.height,
                                                          width=0)
            self.canvas.imagetk = ImageTk.PhotoImage(self.displayed_image)
            self.canvas.create_image(self.canvas.winfo_width() // 2, self.canvas.winfo_height() // 2,
                                     anchor=tk.CENTER, image=self.canvas.imagetk)
            self.center_canvas()

    def center_canvas(self):
        # Move the canvas postion back to the center.
        init_x = (self.canvas.winfo_width() // 2) - (self.width // 2)
        init_y = (self.canvas.winfo_height() // 2) - (self.height // 2)
        tgt_x = int(self.canvas.canvasx(init_x))
        tgt_y = int(self.canvas.canvasy(init_y))
        if init_x != tgt_x or init_y != tgt_y:
            self.canvas.scan_mark(init_x, init_y)
            self.canvas.scan_dragto(tgt_x, tgt_y, gain=1)

    @not_without_file
    def fit_to_window(self, event=None):
        # Resize the image to fit the window
        self.center_canvas()
        init_x = (self.canvas.winfo_width() // 2) - (self.width // 2)
        init_y = (self.canvas.winfo_height() // 2) - (self.height // 2)
        scale = min((self.canvas.winfo_width() - 4) / self.width, (self.canvas.winfo_height() - 4) / self.height)
        self.zoom_factor = scale

        self.container = self.canvas.create_rectangle(init_x, init_y, init_x + self.width, init_y + self.height,
                                                      width=0)
        self.zoom_image(self.canvas.winfo_width() / 2, self.canvas.winfo_height() / 2, scale)
        self.zoomfit_button.state(['pressed'])

    def resize_window(self, *args):
        if 'pressed' in self.zoomfit_button.state():
            self.fit_to_window()
        self.show_image()

    def show_image(self, event=None):
        # Update display of the image on the canvas
        if not self.container or self.canvas.bbox(self.container) is None:
            return
        image_bbox = self.canvas.bbox(self.container)  # get image area
        # Remove 1 pixel shift at the sides of the image_bbox
        image_bbox = (image_bbox[0] + 1, image_bbox[1] + 1, image_bbox[2] - 1, image_bbox[3] - 1)
        visible_bbox = (self.canvas.canvasx(0),  # get visible area of the canvas
                        self.canvas.canvasy(0),
                        self.canvas.canvasx(self.canvas.winfo_width()),
                        self.canvas.canvasy(self.canvas.winfo_height()))
        scroll_bbox = [min(image_bbox[0], visible_bbox[0]), min(image_bbox[1], visible_bbox[1]),
                       max(image_bbox[2], visible_bbox[2]), max(image_bbox[3], visible_bbox[3])]
        if scroll_bbox[0] == visible_bbox[0] and scroll_bbox[2] == visible_bbox[2]:  # whole image in the visible area
            scroll_bbox[0] = image_bbox[0]
            scroll_bbox[2] = image_bbox[2]
        if scroll_bbox[1] == visible_bbox[1] and scroll_bbox[3] == visible_bbox[3]:  # whole image in the visible area
            scroll_bbox[1] = image_bbox[1]
            scroll_bbox[3] = image_bbox[3]
        self.canvas.configure(scrollregion=scroll_bbox)  # set scroll region
        x1 = max(visible_bbox[0] - image_bbox[0], 0)  # get coordinates (x1,y1,x2,y2) of the image tile
        y1 = max(visible_bbox[1] - image_bbox[1], 0)
        x2 = min(visible_bbox[2], image_bbox[2]) - image_bbox[0]
        y2 = min(visible_bbox[3], image_bbox[3]) - image_bbox[1]
        if int(x2 - x1) > 0 and int(y2 - y1) > 0:  # show image if it in the visible area
            # Desired bbox in the original pixel size
            des_x1 = x1 / self.zoom_factor
            des_x2 = x2 / self.zoom_factor
            des_y1 = y1 / self.zoom_factor
            des_y2 = y2 / self.zoom_factor
            des_x_width = int(x2 - x1)
            des_y_height = int(y2 - y1)

            real_x_width = des_x2 - des_x1
            rnd_x_width = math.ceil(des_x2) - math.floor(des_x1)
            tgt_x_width = (des_x_width / real_x_width) * rnd_x_width

            real_y_height = des_y2 - des_y1
            rnd_y_height = math.ceil(des_y2) - math.floor(des_y1)
            tgt_y_height = (des_y_height / real_y_height) * rnd_y_height

            x = des_x_width / rnd_x_width * (des_x1 - math.floor(des_x1))
            y = des_y_height / rnd_y_height * (des_y1 - math.floor(des_y1))

            # First crop to target area, with a whole-pixel border. Scale up, then crop further to the desired subpixels
            image = self.displayed_image.crop((math.floor(des_x1), math.floor(des_y1),
                                               math.ceil(des_x2), math.ceil(des_y2)))
            image = image.resize((int(tgt_x_width), int(tgt_y_height)), resample=INTERP_DEFS[self.interp_mode.get()])
            image = image.crop((x, y, x + des_x_width, y + des_y_height))
            self.canvas.imagetk = ImageTk.PhotoImage(image)

            self.canvas.create_image(max(visible_bbox[0], image_bbox[0]), max(visible_bbox[1], image_bbox[1]),
                                     anchor='nw', image=self.canvas.imagetk)

    def make_file_list(self):
        # Scan the current directory for supported image files.
        directory = os.path.dirname(os.path.abspath(self.file))
        self.file_list = [os.path.normpath(os.path.join(directory, file)) for file in os.listdir(directory) if
                          os.path.splitext(file)[-1].lower() in SUPPORTED_EXTENSIONS]
        self.current_index = self.file_list.index(self.file)

    def open_file(self):
        # Open a file specified with a file dialog
        file = tkfiledialog.askopenfilename()
        if file:
            self.file_list = []
            self.load_image(os.path.normpath(file))

    @not_without_file
    def next_file(self, event=None):
        if event and self.z_label == self.focus_get():
            return
        # Open the next file in the current directory
        if len(self.file_list) == 0:
            self.make_file_list()
        if len(self.file_list) == 1:
            return
        if self.current_index < len(self.file_list) - 1:
            self.current_index += 1
        elif self.current_index == len(self.file_list) - 1:
            self.current_index = 0
        self.zoom_factor = 1
        self.load_image(self.file_list[self.current_index])

    @not_without_file
    def prev_file(self, event=None):
        if event and self.z_label == self.focus_get():
            return
        # Open the previous file in the current directory
        if len(self.file_list) == 0:
            self.make_file_list()
        if len(self.file_list) == 1:
            return
        if self.current_index > 0:
            self.current_index -= 1
        elif self.current_index == 0:
            self.current_index = len(self.file_list) - 1
        self.zoom_factor = 1
        self.load_image(self.file_list[self.current_index])

    def hover_pixel(self, event):
        # Display pixel coordinate and value under the mouse pointer.
        if self.file and self.displayed_image and (box := self.canvas.bbox(self.container)):
            event.x = int((self.canvas.canvasx(event.x) - box[0]) / self.zoom_factor)
            event.y = int((self.canvas.canvasy(event.y) - box[1]) / self.zoom_factor)
            if 0 <= event.y < self.image_data.shape[0] and 0 <= event.x < self.image_data.shape[1]:
                pixel = self.image_data[event.y][event.x]  # Correct for border around label.
                self.xyvalue.set(f"X: {event.x} Y: {event.y}")
                self.pixelvalue.set(pixel)
                return "break"
        self.xyvalue.set("-")
        self.pixelvalue.set("-")
        return "break"

    def no_pixel(self, event):
        # Clear pixel display when not hovering over the image.
        self.xyvalue.set("-")
        self.pixelvalue.set("-")

    def close(self, event=None):
        # Close the window
        # The central window manager may have other windows open, so we need to explicitly close any children.
        if self.info_popup:
            self.info_popup.destroy()
        if self.display_popup:
            self.display_popup.destroy()
        if self.about_popup:
            self.about_popup.destroy()
        self.destroy()
        if not self.master.children:
            # Shut down ImQuick if no other windows are open.
            self.master.destroy()


class InfoPopup(tk.Toplevel):
    # Dialog showing image statistics
    def __init__(self, master, data, file):
        super(InfoPopup, self).__init__()
        self.master = master
        self.filename = ttk.Label(self, text="Info")
        self.title("Image details")
        self.iconbitmap(resource_directory(ICON_FILE))
        self.transient(master)

        self.info = tk.Text(self)

        self.filename.pack()
        self.info.pack(fill=tk.BOTH, expand=True)
        self.show_info(data, file)
        self.protocol('WM_DELETE_WINDOW', self.destroy)
        self.geometry(f"250x150+{min(master.winfo_x() + master.winfo_width(),  self.winfo_screenwidth() - 260)}+"
                      f"{master.winfo_y() + 250}")

    def destroy(self):
        super(InfoPopup, self).destroy()
        self.master.info_popup = None
        # Deregister from the main window manager too.
        if self._name in self.master.master.children:
            del self.master.master.children[self._name]

    def show_info(self, data, file):
        filename = os.path.split(file)[-1]
        self.filename.config(text=filename)
        infotxt = f"""
        Format: {data.dtype}
        Width: {data.shape[1]}px
        Height: {data.shape[0]}px
        Minimum: {data.min()}
        Maximum: {data.max()}
        Unique Values: {len(np.unique(data))}
        """
        self.info.configure(state=tk.NORMAL)
        self.info.delete(1.0, tk.END)
        self.info.insert(tk.INSERT, infotxt)
        self.info.configure(state=tk.DISABLED)


class DisplayPopup(tk.Toplevel):
    # Dialog for contrast adjustment
    def __init__(self, master, file, shape):
        super(DisplayPopup, self).__init__()
        self.master = master
        self.filename = ttk.Label(self, text="Info", anchor=tk.CENTER)
        self.title(f"Adjust Contrast")
        self.resizable(0, 0)
        self.transient(master)
        # Active channel ID
        self.selected = 0
        # Index for channel min-max array channel position
        self.offset = 0
        # Whether to hold off on updating channel array while manipulating sliders
        self.working = False
        self.channel_select = ttk.Combobox(self, state="readonly", values=['All'])
        self.channel_select.bind("<<ComboboxSelected>>", self.channel_mode_select)

        self.min_slider = ttk.Scale(self, variable=master.min_display_value, from_=0, to=255)

        self.max_slider = ttk.Scale(self, variable=master.max_display_value, from_=0, to=255)

        self.columnconfigure(1, weight=3)
        self.rowconfigure(1, weight=1)
        self.rowconfigure(2, weight=1)
        self.filename.grid(column=0, row=0, columnspan=2, sticky=tk.NSEW, pady=5)
        ttk.Label(self, text="Channel:").grid(column=0, row=1, sticky=tk.NSEW, padx=5)
        self.channel_select.grid(column=1, row=1, padx=10)
        ttk.Label(self, text="Min:").grid(column=0, row=2, sticky=tk.NSEW, padx=5)
        ttk.Label(self, text="Max:").grid(column=0, row=3, sticky=tk.NSEW, padx=5)

        self.min_slider.grid(column=1, row=2, sticky=tk.NSEW, padx=10)
        self.max_slider.grid(column=1, row=3, sticky=tk.NSEW, padx=10)

        self.switch_image(file, shape)
        self.protocol('WM_DELETE_WINDOW', self.destroy)
        self.geometry(f"200x150+{min(master.winfo_x() + master.winfo_width(),  self.winfo_screenwidth() - 210)}+"
                      f"{master.winfo_y() + 50}")

    def destroy(self):
        super(DisplayPopup, self).destroy()
        self.master.display_popup = None
        # Deregister from the main window manager too.
        if self._name in self.master.master.children:
            del self.master.master.children[self._name]

    def switch_image(self, file, shape):
        filename = os.path.split(file)[-1]
        self.filename.config(text=filename)
        shape = 0 if len(shape) < 3 else shape[-1]
        self.channel_select.config(values=['All'] + [f'Channel {x}' for x in range(shape)])
        self.channel_select.set('All')
        self.selected = 0
        self.offset = 0
        self.master.per_channel_contrast = False

    def channel_mode_select(self, event=None):
        if self.channel_select.get() == 'All':
            self.master.per_channel_contrast = False
            self.selected = -1
        else:
            self.master.per_channel_contrast = True
            self.selected = int(self.channel_select.get()[-1])
        self.offset = (self.selected + 1) * 2
        self.working = True
        self.master.min_display_value.set(self.master.display_values_array[self.offset])
        self.master.max_display_value.set(self.master.display_values_array[self.offset + 1])
        self.working = False


class AboutPopup(tk.Toplevel):
    # Dialog for info about ImQuick
    def __init__(self, master):
        super(AboutPopup, self).__init__()
        self.master = master
        self.title("About ImQuick")
        self.resizable(0, 0)
        self.transient(master)
        self.logo = Image.open(resource_directory(ICON_FILE)).resize((100, 100))
        self.logoimg = ImageTk.PhotoImage(self.logo)
        tk.Label(self, image=self.logoimg).pack(pady=(15, 0))
        tk.Label(self, text="ImQuick", font=("Arial", 18), justify=tk.CENTER).pack()
        tk.Label(self, text="Version " + __version__, font=("Consolas", 10), justify=tk.CENTER).pack(pady=(0, 5))
        tk.Label(self, text="David Stirling, 2021", font=("Arial", 10), justify=tk.CENTER).pack()
        tk.Label(self, text="@DavidRStirling", font=("Arial", 10), justify=tk.CENTER).pack(pady=(0, 15))
        self.protocol('WM_DELETE_WINDOW', self.destroy)
        self.geometry(f"250x250+{master.winfo_x() // 2 + (master.winfo_width() // 2)}+"
                      f"{master.winfo_y() // 2 + (master.winfo_height() // 2)}")

    def destroy(self):
        super(AboutPopup, self).destroy()
        self.master.about_popup = None
        # Deregister from the main window manager too.
        if self._name in self.master.master.children:
            del self.master.master.children[self._name]


def rescale_data(data):
    maxval = data.max()
    if maxval >= 4096:
        out = data / 265
    elif maxval >= 1024:
        out = data / 16
    elif maxval >= 256:
        out = data / 4
    elif maxval <= 1:
        out = data * 256
    else:
        out = data
    return out.astype('uint8')


def docs():
    import webbrowser
    webbrowser.open("https://github.com/DavidStirling/ImQuick")


def _load_tkdnd(master):
    # Loads the DND plugin from the packed-in directory
    master.tk.eval('global auto_path; lappend auto_path {tkdnd}')
    master.tk.eval('package require tkdnd')
    master._tkdnd_loaded = True


def resource_directory(target):
    if '__compiled__' in globals():
        return os.path.join(sys.prefix, 'resources', target)
    else:
        return os.path.join('resources', target)


if __name__ == '__main__':
    if len(sys.argv) > 1:
        file_in = sys.argv[1]
    else:
        file_in = ''
    root = tkDnD.TkinterDnD.Tk()
    style = ttk.Style()
    if sys.platform == "win32":
        root.iconbitmap(True, resource_directory(ICON_FILE))
    else:
        root.icon = tk.PhotoImage(file=resource_directory(ICON_FILE))
        root.wm_iconphoto(True, root.icon)
        if sys.platform == 'darwin':
            root.tk_setPalette(background='#D9D9D9', selectForeground='#ffffff', selectBackground='#0000ff')
            try:
                style.theme_use('alt')
            except Exception as e:
                print("Unable to set theme, icons may look strange: ", e)
    style.configure('mini.TButton', justify='center', width=3, height=1, state='!disabled')

    root.wm_title("I am the window manager. If you can see me, something isn't right")
    root.withdraw()
    _load_tkdnd(root)
    app = ImQuick(root, file_in)
    root.mainloop()
