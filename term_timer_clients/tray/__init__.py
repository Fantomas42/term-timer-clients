"""
The cube in the bar of the desktop, and the window a click on it opens.

Everything here runs in the ``cube-tray`` process, which holds no cube
and draws none: it subscribes to the stream to know whether there is
one, and the window showing it is ``cube-cast``, opened aside. Two
processes because they are two loops - the bus wants a thread and glfw
wants the one that opened its window - and because a publisher binding
for everybody is exactly what lets two clients listen at once.
"""
