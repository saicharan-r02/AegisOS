class Broker:
    def __init__(self):
        self.listeners = []
    def subscribe(self, fn):
        self.listeners.append(fn)
    def dispatch(self, msg):
        for fn in self.listeners:
            fn(msg)
