class BrokenAlgorithm:
    """Example of an invalid algorithm - missing run method"""
    
    def __init__(self):
        pass
    
    # Missing run(nodes, step_count) method!
    def execute(self, nodes):
        print("This won't work!")
