"""
Out of process 3D visualisation of the cube.

Everything here runs in the ``cubecast`` process, which subscribes to
the event stream and draws what it hears. The process timing the solves
never loads a GPU driver, so no crash of one can reach a session.
"""
