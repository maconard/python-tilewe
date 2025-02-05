import random
import time

import tilewe 

class Engine: 
    """
    Developers should extend this class to build their own engine.
    Currently requires overriding the `on_search` function which must
    return one legal move within the given time control.

    For extension examples, see the Sample Engines below.
    For construction examples, see the tilewe.tournament.Tournament class.
    """
    
    def __init__(self, name: str): 
        self.name = name  
        self.seconds = 0 
        self.end_at = time.time() 

    def out_of_time(self) -> bool: 
        return time.time() >= self.end_at 

    def search(self, board: tilewe.Board, seconds: float) -> tilewe.Move: 
        self.end_at = time.time() + seconds 
        self.seconds = seconds 
        return self.on_search(board, seconds) 

    def on_search(self, board: tilewe.Board, seconds: float) -> tilewe.Move: 
        raise NotImplementedError() 

"""
Sample Engines

The following engines implement fairly simple strategies and can
be used for testing your Engine against in tournaments.
Approximate strength ordering:
    WallCrawlerEngine, very weak
    RandomEngine, very weak
    MostOpenCornersEngine, weak
    LargestPieceEngine, moderate
    MaximizeMoveDifferenceEngine, surprisingly strong
"""

class MoveExecutor(object):
    """
    Helper for testing board state after applying a move when
    you intend to pop that move afterwards. See example usage
    in the Sample Engines below.
    """
    
    def __init__(self, board: tilewe.Board, move: tilewe.Move):
        self.board = board
        self.move = move
    
    def __enter__(self):
        self.board.push(self.move)

    def __exit__(self, *args):
        self.board.pop()

class RandomEngine(Engine): 
    """
    Literally just selects a random move from all legal moves.
    Pretty bad, but makes moves really fast.
    """

    def __init__(self, name: str="Random"): 
        super().__init__(name)

    def on_search(self, board: tilewe.Board, _seconds: float) -> tilewe.Move: 
        return random.choice(board.generate_legal_moves(unique=True)) 

class MostOpenCornersEngine(Engine): 
    """
    Plays the move that results in the player having the most
    playable corners possible afterwards, i.e. maximizing the
    possible moves on the next turn.
    Fairly weak but does result in decent board coverage behavior.
    """

    def __init__(self, name: str="MostOpenCorners"):
        super().__init__(name)

    def on_search(self, board: tilewe.Board, _seconds: float) -> tilewe.Move:
        moves = board.generate_legal_moves(unique=True) 
        random.shuffle(moves) 
        
        player = board.current_player

        def corners_after_move(m: tilewe.Move) -> int: 
            with MoveExecutor(board, m):
                corners = board.n_player_corners(player) 
                return corners

        return max(moves, key=corners_after_move)

class LargestPieceEngine(Engine): 
    """
    Plays the best legal move prioritizing the following, in order:
        Piece with the most squares (i.e. most points)
        Piece that introduces the most corners
        Piece that has the most contacts
    Moderately strong from a greedy point hungry perspective. Since
    ties are common and result in a random move choice across the
    ties, it's effectively a greedy form of RandomEngine.
    """

    def __init__(self, name: str="LargestPiece"):
        super().__init__(name)

    def on_search(self, board: tilewe.Board, _seconds: float) -> tilewe.Move:
        moves = board.generate_legal_moves(unique=True) 
        random.shuffle(moves) 

        best = max(moves, key=lambda m:
            tilewe.n_piece_tiles(m.piece) * 100 +
            tilewe.n_piece_corners(m.piece) * 10 +
            tilewe.n_piece_contacts(m.piece))
        
        return best

class MaximizeMoveDifferenceEngine(Engine): 
    """
    Plays the move that results in the player having the best difference 
    in subsequent legal move counts compared to all opponents. That is,
    how many legal moves the player has following this move minus how many
    legal moves all the opponents have following this move.
    Surprisingly strong due to implicitly incorporating various heuristics
    that result in behaviors seeking more open corners, blocking opponent corners, 
    getting access to an open area on the board, etc.
    """

    def __init__(self, name: str="MaximizeMoveDifference"):
        super().__init__(name)

    def on_search(self, board: tilewe.Board, _seconds: float) -> tilewe.Move:
        moves = board.generate_legal_moves(unique=True) 
        random.shuffle(moves) 
        
        player = board.current_player

        def eval_after_move(m: tilewe.Move) -> int: 
            with MoveExecutor(board, m):
                total = 0
                for color in range(board.n_players): 
                    n_moves = board.n_legal_moves(unique=True, for_player=color)
                    total += n_moves * (1 if color == player else -1)
                return total

        return max(moves, key=eval_after_move)
    
class TileWeightEngine(Engine):
    """
    Evalutes tile ownership after each legal move and selects the move that maximizes
    ownership of tiles with the highest scores. Supports the built-in weight maps below
    and passing in your own custom set of tile weights, which must be a list of 400 values.
    Note that weights are ordered [A01, A02, ..., A20, B01, B02, ..., S20, T01, T02, ..., T20].

    Strength depends entirely on the strategy encapsulated by the given weights!
        'wall_crawl' seems moderate (better than random/open corners but weaker than others)
        'turtle' seems fairly weak (better than random but weaker than others)
    """

    WALL_CRAWL_WEIGHTS: list[int] = [
        100, 100, 100, 100, 100, 100, 100, 100, 100, 100, 100, 100, 100, 100, 100, 100, 100, 100, 100, 100,  # noqa: 241
        100, 90,  90,  90,  90,  90,  90,  90,  90,  90,  90,  90,  90,  90,  90,  90,  90,  90,  90,  100,  # noqa: 241
        100, 90,  75,  75,  75,  75,  75,  75,  75,  75,  75,  75,  75,  75,  75,  75,  75,  75,  90,  100,  # noqa: 241
        100, 90,  75,  60,  60,  60,  60,  60,  60,  60,  60,  60,  60,  60,  60,  60,  60,  75,  90,  100,  # noqa: 241
        100, 90,  75,  60,  50,  50,  50,  50,  50,  50,  50,  50,  50,  50,  50,  50,  60,  75,  90,  100,  # noqa: 241
        100, 90,  75,  60,  50,  40,  40,  40,  40,  40,  40,  40,  40,  40,  40,  50,  60,  75,  90,  100,  # noqa: 241
        100, 90,  75,  60,  50,  40,  30,  30,  30,  30,  30,  30,  30,  30,  40,  50,  60,  75,  90,  100,  # noqa: 241
        100, 90,  75,  60,  50,  40,  30,  25,  25,  25,  25,  25,  25,  30,  40,  50,  60,  75,  90,  100,  # noqa: 241
        100, 90,  75,  60,  50,  40,  30,  25,  10,  10,  10,  10,  25,  30,  40,  50,  60,  75,  90,  100,  # noqa: 241
        100, 90,  75,  60,  50,  40,  30,  25,  10,  0,   0,   10,  25,  30,  40,  50,  60,  75,  90,  100,  # noqa: 241
        100, 90,  75,  60,  50,  40,  30,  25,  10,  0,   0,   10,  25,  30,  40,  50,  60,  75,  90,  100,  # noqa: 241
        100, 90,  75,  60,  50,  40,  30,  25,  10,  10,  10,  10,  25,  30,  40,  50,  60,  75,  90,  100,  # noqa: 241
        100, 90,  75,  60,  50,  40,  30,  25,  25,  25,  25,  25,  25,  30,  40,  50,  60,  75,  90,  100,  # noqa: 241
        100, 90,  75,  60,  50,  40,  30,  30,  30,  30,  30,  30,  30,  30,  40,  50,  60,  75,  90,  100,  # noqa: 241
        100, 90,  75,  60,  50,  40,  40,  40,  40,  40,  40,  40,  40,  40,  40,  50,  60,  75,  90,  100,  # noqa: 241
        100, 90,  75,  60,  50,  50,  50,  50,  50,  50,  50,  50,  50,  50,  50,  50,  60,  75,  90,  100,  # noqa: 241
        100, 90,  75,  60,  60,  60,  60,  60,  60,  60,  60,  60,  60,  60,  60,  60,  60,  75,  90,  100,  # noqa: 241
        100, 90,  75,  75,  75,  75,  75,  75,  75,  75,  75,  75,  75,  75,  75,  75,  75,  75,  90,  100,  # noqa: 241
        100, 90,  90,  90,  90,  90,  90,  90,  90,  90,  90,  90,  90,  90,  90,  90,  90,  90,  90,  100,  # noqa: 241
        100, 100, 100, 100, 100, 100, 100, 100, 100, 100, 100, 100, 100, 100, 100, 100, 100, 100, 100, 100,  # noqa: 241
    ]

    TURTLE_WEIGHTS: list[int] = [
        512, 256, 128, 64, 32, 16, 8, 4, 2, 1, 1, 2, 4, 8, 16, 32, 64, 128, 256, 512,  # noqa: 241
        256, 256, 128, 64, 32, 16, 8, 4, 2, 1, 1, 2, 4, 8, 16, 32, 64, 128, 256, 256,  # noqa: 241
        128, 128, 128, 64, 32, 16, 8, 4, 2, 1, 1, 2, 4, 8, 16, 32, 64, 128, 128, 128,  # noqa: 241
        64,  64,  64,  64, 32, 16, 8, 4, 2, 1, 1, 2, 4, 8, 16, 32, 64, 64,  64,  64,   # noqa: 241
        32,  32,  32,  32, 32, 16, 8, 4, 2, 1, 1, 2, 4, 8, 16, 32, 32, 32,  32,  32,   # noqa: 241
        16,  16,  16,  16, 16, 16, 8, 4, 2, 1, 1, 2, 4, 8, 16, 16, 16, 16,  16,  16,   # noqa: 241
        8,   8,   8,   8,  8,  8,  8, 4, 2, 1, 1, 2, 4, 8, 8,  8,  8,  8,   8,   8,    # noqa: 241
        4,   4,   4,   4,  4,  4,  4, 4, 2, 1, 1, 2, 4, 4, 4,  4,  4,  4,   4,   4,    # noqa: 241
        2,   2,   2,   2,  2,  2,  2, 2, 2, 1, 1, 2, 2, 2, 2,  2,  2,  2,   2,   2,    # noqa: 241
        1,   1,   1,   1,  1,  1,  1, 1, 1, 1, 1, 1, 1, 1, 1,  1,  1,  1,   1,   1,    # noqa: 241
        1,   1,   1,   1,  1,  1,  1, 1, 1, 1, 1, 1, 1, 1, 1,  1,  1,  1,   1,   1,    # noqa: 241
        2,   2,   2,   2,  2,  2,  2, 2, 2, 1, 1, 2, 2, 2, 2,  2,  2,  2,   2,   2,    # noqa: 241
        4,   4,   4,   4,  4,  4,  4, 4, 2, 1, 1, 2, 4, 4, 4,  4,  4,  4,   4,   4,    # noqa: 241
        8,   8,   8,   8,  8,  8,  8, 4, 2, 1, 1, 2, 4, 8, 8,  8,  8,  8,   8,   8,    # noqa: 241
        16,  16,  16,  16, 16, 16, 8, 4, 2, 1, 1, 2, 4, 8, 16, 16, 16, 16,  16,  16,   # noqa: 241
        32,  32,  32,  32, 32, 16, 8, 4, 2, 1, 1, 2, 4, 8, 16, 32, 32, 32,  32,  32,   # noqa: 241
        64,  64,  64,  64, 32, 16, 8, 4, 2, 1, 1, 2, 4, 8, 16, 32, 64, 64,  64,  64,   # noqa: 241
        128, 128, 128, 64, 32, 16, 8, 4, 2, 1, 1, 2, 4, 8, 16, 32, 64, 128, 128, 128,  # noqa: 241
        256, 256, 128, 64, 32, 16, 8, 4, 2, 1, 1, 2, 4, 8, 16, 32, 64, 128, 256, 256,  # noqa: 241
        512, 256, 128, 64, 32, 16, 8, 4, 2, 1, 1, 2, 4, 8, 16, 32, 64, 128, 256, 512,  # noqa: 241
    ]

    weight_maps = {
        'wall_crawl': WALL_CRAWL_WEIGHTS,
        'turtle': TURTLE_WEIGHTS
    }

    def __init__(self, name: str="TileWeight", weight_map: str='wall_crawl', custom_weights: list[int | float]=None): 
        """
        Current `weight_map` built-in options are 'wall_crawl' and 'turtle'
        Can optionally provide a custom set of weights instead
        """

        super().__init__(name)

        if custom_weights is not None:
            if len(custom_weights) != 20 * 20:
                raise Exception("TileWeightEngine custom_weights must be a list of exactly 400 values")
            self.weights = custom_weights
        
        else:
            if weight_map not in self.weight_maps:
                raise Exception("TileWeightEngine given invalid weight_map choice")
            self.weights = self.weight_maps[weight_map]

    def on_search(self, board: tilewe.Board, _seconds: float) -> tilewe.Move: 

        cur_player = board.current_player

        def evaluate_move_weight(move: tilewe.Move) -> float: 
            total: float = 0.0

            to_coords = tilewe.tile_to_coords(move.to_tile) 
            for coords in tilewe.piece_tile_coords(move.piece, move.rotation, move.contact): 
                coords = (coords[0] + to_coords[0], coords[1] + to_coords[1])
                total += self.weights[coords[1] * 20 + coords[0]]

            return total

        moves = board.generate_legal_moves(unique=True)
        random.shuffle(moves)

        if board.ply < board.n_players:
            #  prune to one corner to reduce moves to evaluate
            corner = board.player_corners(cur_player)[0]
            moves = [i for i in moves if i.to_tile == corner]

        return max(moves, key=evaluate_move_weight)
