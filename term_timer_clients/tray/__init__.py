"""
The cube in the bar of the desktop, and the window a click on it shows.

Everything here runs in the ``cube-tray`` process, which holds no cube
and draws none: it subscribes to the stream to know whether there is
one, and the window showing it is ``cube-cast``, opened aside. Two
processes because they are two loops - the bus wants a thread and glfw
wants the one that opened its window - and because a publisher binding
for everybody is exactly what lets two clients listen at once.

That window is opened with the icon and hidden behind it, rather than
started at the click: a cube describes itself when it connects and
announces nothing when it arrives, so a window started in the middle of
a session has heard neither and shows nothing of the cube. What a click
carries is a word on the pipe the window reads its orders on.
"""
