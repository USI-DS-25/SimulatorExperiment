import random


class RandomTraffic:
    def __init__(self):
        pass

    def run(self, nodes, step_count):
        """
        Executes the random traffic generation logic.

        Args:
            nodes (list): List of VisualNode objects.
            step_count (int): Current simulation step count.
        """
        if random.random() < 0.3 and nodes:
            # Pick a random node to send a message
            sender = random.choice(nodes)
            peers = [n for n in nodes if n.node_id != sender.node_id]
            if peers:
                target = random.choice(peers)
                sender.send(f"PING-{step_count}", target=target.node_id)

        # Process received messages (Algorithm Logic)
        for node in nodes:
            while node.inbox:
                msg = node.inbox.pop(0)
                if "PING" in str(msg):
                    # Reply with PONG
                    # Find sender from message if possible, or just broadcast/log
                    # Since message is just a string here, we assume we reply to someone.
                    # But wait, the original code didn't know the sender from the string "PING".
                    # The VisualNetwork.send logs src/dst, but the message itself is just payload.
                    # Let's assume the message format is simple string.
                    # To reply, we need to know who sent it.
                    # The current simple implementation doesn't pass sender info in the message payload.
                    # However, for this demo, let's just make the node send a "PONG" to a random peer
                    # OR we can improve the message format.

                    # For now, let's just log that we processed it, or send a PONG to a random peer to keep traffic moving.
                    # Ideally, the message should be a dict or object with 'sender'.
                    pass

                # Let's implement a simple "Reply to Sender" if we can infer it,
                # otherwise just send a PONG to a random neighbor to simulate traffic.
                if "PING" in str(msg):
                    peers = [n for n in nodes if n.node_id != node.node_id]
                    if peers:
                        # In a real algo, we'd extract sender from msg.
                        # Here we just pick a random target to keep the visual interesting.
                        target = random.choice(peers)
                        node.send(f"PONG-{step_count}", target=target.node_id)
