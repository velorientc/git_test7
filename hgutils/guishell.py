"""
Execute a Mercurial (Hg) command and show it's output on the Tkinter window.

Based on the recipe post on ActiveState Programmer Network, titled
'Threads, Tkinter and asynchronous I/O':

    http://aspn.activestate.com/ASPN/Cookbook/Python/Recipe/82965

Copyright (c) 2007 TK Soh 

email: teekaysoh@yahoo.com
       teekaysoh@gmail.com

"""
import sys, subprocess
from Tkinter import *
import ScrolledText
import threading
import Queue
import time

class GuiPart:
    def __init__(self, master, queue, endCommand):
        self.queue = queue
        
        # === Set up the GUI ===
        
        # show user commands
        frame = Frame(master)
        frame.pack(side=TOP, fill='x', padx=2, pady=2)
        lbl1 = Label(frame, text='Command:')
        lbl1.pack(side=LEFT)
        self.cmdtext = Text(frame, heigh=1)
        self.cmdtext.pack(side=RIGHT, fill='x', expand=1)
        
        # text widget to display output message from hg commands
        self.outtext = ScrolledText.ScrolledText(master)
        self.outtext.config(font="Courier 8")
        self.outtext.pack(side=TOP, fill='both', expand=1)
        
        # click this to exit
        console = Button(master, text='Close', command=endCommand)
        console.pack(pady=5, side=BOTTOM)

    def setCommandText(self, cmd):
        self.cmdtext.config(state=NORMAL)
        self.cmdtext.insert(END, ' '.join(cmd))
        self.cmdtext.config(state=DISABLED)
        
    def processIncoming(self):
        """
        Handle all the messages currently in the queue (if any).
        """
        while self.queue.qsize():
            try:
                msg = self.queue.get(0)

                # show hg command output on text widget (readonly)
                self.outtext.config(state=NORMAL)
                self.outtext.insert(END, str(msg))
                self.outtext.config(state=DISABLED)
            except Queue.Empty:
                pass

class ThreadedClient:
    """
    Launch the main part of the GUI and the worker thread. periodicCall and
    endApplication could reside in the GUI part, but putting them here
    means that you have all the thread controls in a single place.
    """
    def __init__(self, master, cmd):
        """
        Start the GUI and the asynchronous threads. We are in the main
        (original) thread of the application, which will later be used by
        the GUI. We spawn a new thread for the worker.
        """
        self.master = master
        self.pop = None

        # Create the queue
        self.queue = Queue.Queue()

        # Set up the GUI part
        self.gui = GuiPart(master, self.queue, self.endApplication)
        self.gui.setCommandText(cmd)

        # Set up the thread to do asynchronous I/O
        # More can be made if necessary
        self.running = 1
        self.cmdline = cmd
    	self.thread1 = threading.Thread(target=self.runProgram)
        self.thread1.start()

        # Start the periodic call in the GUI to check if the queue contains
        # anything
        self.periodicCall()

    def periodicCall(self):
        """
        Check every 100 ms if there is something new in the queue.
        """
        self.gui.processIncoming()
        if not self.running:
            # This is the brutal stop of the system. You may want to do
            # some cleanup before actually shutting it down.
            if self.pop and self.pop.poll():
                import os
                pid = self.pop.pid
                if os.name == 'nt':
                    import win32api
                    handle = win32api.OpenProcess(1, 0, pid)
                    win32api.TerminateProcess(handle, 0)
                else:
                    import signal
                    os.kill(pid, signal.SIGINT)
                print "killed pid: ", pid
            import sys
            sys.exit(1)
        self.master.after(100, self.periodicCall)

    def runProgram(self):
        #print "runProgram:", self.cmdline
        self.pop = subprocess.Popen(self.cmdline, 
                               shell=True,
                               stderr=subprocess.STDOUT,
                               stdout=subprocess.PIPE,
                               stdin=subprocess.PIPE)

        try:
            #print "checking popen"
            while self.pop.poll() == None:
                #print "reading pop"
                out = self.pop.stdout.readline()
                if out: self.queue.put(out)
                #time.sleep(0.001)
            #print "popen closed"
            out = self.pop.stdout.read()
            if out: self.queue.put(out)
        except IOError:
            pass
        
        self.pop = None
        #print "done runProgram"

    def endApplication(self):
        self.running = 0

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print "need commands"
        sys.exit(1)

    root = Tk()
    client = ThreadedClient(root, sys.argv[1:])
    root.mainloop()
