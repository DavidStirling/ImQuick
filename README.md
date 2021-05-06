# ImQuick
A lightweight scientific image viewer written in Python.

[![Version](https://img.shields.io/badge/Version-0.5-green.svg)](https://github.com/DavidStirling/ImQuick/releases)

---

There are several amazing image viewing and editing appliations geared towards the scientific community. However, many of these packages suffer from slow startup times and a lack of integration into the system shell. For researchers it can be frustrating to have to launch these very feature-rich applications just to view a file or determine signal strength. Windows includes it's own image previewer, but this lacks some key features which are helpful to visualise and understand raw scientific data.

ImQuick has therefore been designed as a lightweight viewer with some of those useful tools built-in. Viewing an image needs to be fast and painless. The priorities for this project are therefore in startup speed, OS integration and minimal dependencies/bulk. To that end ImQuick is explicitly not an image editor, consider it as a viewer only.

## Installation

Run the setup.exe file [from the releases page](https://github.com/DavidStirling/ImQuick/releases). Only Windows is currently supported (sorry!).

## Key Features

![image](https://user-images.githubusercontent.com/26802537/117225458-5a0ccd00-ade0-11eb-9d4e-a45b328b5767.png)


When installed, image files can be loaded into the viewer using the 'ImQuick' option added to the right-click context menu for image files. You can also drag images onto an existing ImQuick window, or set the program as the default viewer if you like. The UI also has buttons for cycling through images in a directory.

Pan/Zoom can be performed with the mouse and mousewheel, or the dedicated icons. You'll also find icons to view the image at actual size, and to fit the current image to the window.

Contrast adjustment can be performed by opening the contrast dialog using the dedicated button. The sliders in this window set the minimum and maximum intensity to display. The main window also features an 'auto contrast' button to automatically set these scales based on data present in the image itself.

Hovering over a pixel on the image will display it's x/y coordinate and intensity value in the top right corner. Colour images will display intensity in R-G-B or R-G-B-A order.


## Format support

This is a tricky area. Currently ImQuick supports most common image formats (e.g. .tif, .png, .jpeg). The bioimaging space is somewhat overrun with proprietary formats to the point that supporting them all in a lightweight package may be very difficult. If support for a format would be particularly valuable please do raise an issue requesting it.

Right now (in beta) ImQuick can open 2D images. Support for 3D Z-stacks and time series images is hopefully coming soon. Faster loading of some compressed formats is also an area being pursued.


## Setup from source

These instructions are specific to Windows. Without access to a Mac building for that OS is difficult, but if you're interested in helping out please do get in touch.

First off, `git clone` this repository. You'll want Python 3.8+ installed and possibly a virtual env. Once that's set up, copy files from the latest [tkdnd build](https://github.com/petasis/tkdnd) into a `tkdnd` directory in the ImQuick root. This is an extension which adds drag and drop support to the Tkinter GUI toolkit.

To make matters more complicated, you'll also need the `tkinterdnd` Python wrapper module [from here](https://sourceforge.net/projects/tkinterdnd/). It's not available on PyPi, so you'll need to copy this into the site-packages folder of your environment to install manually.

With that done, `pip install -e .` in the repository directory should install all the other dependencies. You can run `ImQuick.py` to start.


## Packaging

ImQuick is currently packaged for Windows using Nuitka and Inno Setup.

Use the following command from the main directory:

```
python -m nuitka --mingw64 --standalone --plugin-enable=tk-inter --plugin-enable=numpy --include-data-file=resources/*=resources/ --include-data-file=tkdnd/*=tkdnd/ --windows-icon-from-ico=resources\ImQuick.ico --windows-disable-console --python-flag=no_site ImQuick.py 
```

This will generate the required files in `\ImQuick.dist`. Execute `imquick.iss` using Inno Setup to pack the .exe into an installer.

