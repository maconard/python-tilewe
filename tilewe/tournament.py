from dataclasses import dataclass, field
import multiprocessing
import traceback
import platform
import random
import signal
import time

import tilewe 
from tilewe.engine import Engine
from tilewe.elo import compute_elo_adjustment_n

@dataclass
class MatchData:
    """
    The data from a single match of Tilewe.

    Parameters
    ----------
    board : tilewe.Board
        A reference to the final board state of the game
    engines : list[int]
        List of the engines that played in the game
    player_to_engine : list[int]
        Ordered list that maps index as player turn order to engine at that turn order
    run_time : float
        The duration of this match in seconds
    elo_start : list[float] | None
        Player Elos before this match
    elo_delta : list[float] | None
        Change in player Elos as a result of this match
    elo_end : list[float] | None
        Player Elos after this match
    """

    board: tilewe.Board
    engines: list[int]
    player_to_engine: list[int]
    run_time: float
    elo_start: list[float] = field(default_factory=list)
    elo_delta: list[float] = field(default_factory=list)
    elo_end: list[float] = field(default_factory=list)

@dataclass
class TournamentResults:
    """
    The data set generated by an instance of Tournament.play.
    Contains the match data and aggregate data.

    Parameters
    ----------
    match_data : list[MatchData]
        List of match specific data for each match in the tournament
    engine_names : list[str]
        List of engine names that played in the tournament
    game_counts : list[int]
        List of game count played by each engine
    win_counts : list[int]
        List of win count by each engine
    total_scores : list[int]
        List of total scores earned by each engine
    elo_start : list[float]
        Engine Elos at the start of the tournament
    elo_end : list[float]
        Engine Elos at the end of the tournament
    real_time : float
        The real run time of the tournament in seconds
    total_time : float
        The total run time of all the individual games in seconds
    """

    match_data: list[MatchData]
    engine_names: list[str]
    game_counts: list[int]
    win_counts: list[int]
    total_scores: list[int]
    elo_start: list[float]
    elo_end: list[float]
    real_time: float
    total_time: float
    
    @property
    def total_games(self) -> int:
        return len(self.match_data)
    
    @property
    def total_engines(self) -> int:
        return len(self.engine_names)

    @property
    def win_rates(self) -> list[float]: 
        return [self.win_counts[i] / max(1, self.game_counts[i]) for i in range(self.total_engines)]
    
    @property
    def avg_scores(self) -> list[float]: 
        return [self.total_scores[i] / max(1, self.game_counts[i]) for i in range(self.total_engines)]

    @property
    def average_match_duration(self) -> float:
        return self.total_time / max(1, self.total_games)
    
    def get_matches_by_engine(self, engine: int) -> list[MatchData]:
        filtered_matches = [x for x in self.match_data if engine in x.engines]
        return filtered_matches
    
    def get_game_count_by_engine(self, engine: int) -> int:
        return self.game_counts[engine]
    
    def get_wins_by_engine(self, engine: int) -> int:
        return self.win_counts[engine]
    
    def get_win_rate_by_engine(self, engine: int) -> float:
        return self.win_counts[engine] / max(1, self.game_counts[engine])
    
    def get_score_by_engine(self, engine: int) -> int:
        return self.total_scores[engine]
    
    def get_avg_score_by_engine(self, engine: int) -> float:
        return self.total_scores[engine] / max(1, self.game_counts[engine])
    
    def get_starting_elo_by_engine(self, engine: int) -> int:
        return self.elo_start[engine]
    
    def get_ending_elo_by_engine(self, engine: int) -> int:
        return self.elo_end[engine]
    
    def get_delta_elo_by_engine(self, engine: int) -> int:
        return self.elo_end[engine] - self.elo_start[engine]
    
    def get_engine_rankings_display(self, sort_by: str = 'elo_end', sort_dir: str = 'desc') -> str:
        if not hasattr(self, sort_by):
            return f"Invalid sort field '{sort_by}', must specify a valid TournamentResults property"
        sort_attr: list = getattr(self, sort_by)
        if not isinstance(sort_attr, list) or len(sort_attr) <= 0:
            return f"Invalid sort field '{sort_by}', must specify a list of length >0"
        if not isinstance(sort_attr[0], int) and not isinstance(sort_attr[0], float):
            return f"Invalid sort field '{sort_by}', must specify a numeric list"
        if sort_dir != 'asc' and sort_dir != 'desc':
            return f"Invalid sort direction '{sort_dir}', try 'asc' or 'desc'"

        out = f"Ranking by {sort_by} {sort_dir}:\n"
        out += f"{'Rank':4} {'Name':24} {'Elo':>5} {'Games':>6} {'Score':>10} {'Avg Score':>10} {'Wins':>6} {'Win Rate':>9}\n"
        dir = -1 if sort_dir == 'desc' else 1
        ranked_engines = sorted(range(len(self.engine_names)), key=lambda x: dir * sort_attr[x])
        for rank, engine in enumerate(ranked_engines):
            name = self.engine_names[engine]
            wins, games = self.win_counts[engine], self.game_counts[engine]
            score, elo = self.total_scores[engine], self.elo_end[engine]

            win_rate = f"{(wins / games * 100):>8.2f}%" if games > 0 else f"{'-':>9}"
            avg_score = f"{(score / games):>10.2f}" if games > 0 else f"{'-':>10}"

            out += f"{rank:>4d} {name:24.24} {elo:>5.0f} {games:>6d} {score:>10d} {avg_score} {wins:>6d} {win_rate}\n"
        return out

class Tournament: 
    """
    Provides an easy construct for testing large amounts of games
    for any amount of engines above 0. Utilizes multiprocessing to play many
    games at once. Handles randomizing turn order and reports on 
    win/score results after each game completes. Currently does
    not enforce time controls, but Engines should follow them anyways.

    Example
    -------
    >>> tournament = tilewe.tournament.Tournament([
        tilewe.engine.LargestPieceEngine(), 
        tilewe.engine.MostOpenCornersEngine(), 
        tilewe.engine.MaximizeMoveDifferenceEngine(), 
        tilewe.engine.RandomEngine()
    ], move_seconds=30)
    >>> tournament.play(1000, n_threads=multiprocessing.cpu_count(), move_seconds=15)
    """

    def __init__(self, engines: list[Engine], move_seconds: int=60):
        """
        Parameters
        ----------
        n_games : int
            The number of games to play
        engines : list[Engine]
            The list of engines to play in the games (at least 1)
        move_seconds : int=60
            The default time control if `play` doesn't override it
        """
        
        if (len(engines) < 1):
            raise Exception("Number of engines must be greater than 0")
        if move_seconds <= 0:
            raise Exception("Must allow greater than 0 seconds per move")
        
        self.engines = list(engines)
        self._seconds = move_seconds
        self.move_seconds = self._seconds

    def play(
        self,
        n_games: int,
        n_threads: int=1,
        players_per_game: int=4,
        move_seconds: int=None,
        verbose_board: bool=False,
        verbose_rankings: bool=True
    ):
        """
        Used to launch a series of games in an initialized Tournament.

        Parameters
        ----------
        n_games : int
            The number of games to play
        n_threads : int=1
            The number of simultaneous games to multiprocess
        players_per_game : int=4
            The amount of players to have in each game, from 1 to 4
        move_seconds : int=60
            Optional override for the time control for these games
        verbose_board : bool=False
            Whether or not to print the final board state of each match
        verbose_rankings : bool=True
            Whether or not to print periodic ranking updates and the final rankings at the end
        """

        if n_games <= 0:
            raise Exception("Must play at least one game")
        if n_threads <= 0:
            raise Exception("Must use at least one thread")
        if players_per_game < 1 or players_per_game > 4:
            raise Exception("Must have 1 to 4 players per game")
        
        self.move_seconds = move_seconds if move_seconds is not None else self._seconds
        if self.move_seconds <= 0:
            raise Exception("Must allow greater than 0 seconds per move")
        
        # initialize trackers and game controls
        N = len(self.engines)
        total_games = 0
        wins = [0 for _ in range(N)]
        games = [0 for _ in range(N)]
        elos = [0 for _ in range(N)]
        totals = [0 for _ in range(N)]

        initial_elos = [i for i in elos]
        match_results: list[MatchData] = []

        # helper for getting engine rank summaries
        def get_engine_rankings() -> str:
            out = f"\n{'Rank':4} {'Name':24} {'Elo':>5} {'Games':>6} {'Score':>10} "
            out += f"{'Avg Score':>10} {'Wins':>6} {'Win Rate':>9}\n"
            ranked_engines = sorted(range(N), key=lambda x: -elos[x])
            for rank, engine in enumerate(ranked_engines):
                name = self.engines[engine].name
                win_count, game_count = wins[engine], games[engine]
                score, elo = totals[engine], elos[engine]
                
                win_rate = f"{(win_count / game_count * 100):>8.2f}%" if game_count > 0 else f"{'-':>9}"
                avg_score = f"{(score / game_count):>10.2f}" if game_count > 0 else f"{'-':>10}"

                out += f"{rank:>4d} {name:24.24} {elo:>5.0f} {game_count:>6d} {score:>10d} "
                out += f"{avg_score} {win_count:>6d} {win_rate}\n"
            return out

        # prepare turn orders for the various games
        args = [] 
        for _ in range(n_games): 
            order = list(range(N))
            random.shuffle(order) 
            args.append(order[:players_per_game]) 

        # play games with the given level of concurrency
        start_time = time.time()
        total_time = 0.0

        if platform.system() == "Windows":
            init_func, init_args = [None, None]
        else:
            init_func, init_args = [signal.signal, (signal.SIGINT, signal.SIG_IGN)]

        with multiprocessing.Pool(n_threads, initializer=init_func, initargs=init_args) as pool: 
            try:
                for winners, scores, board, player_to_engine, time_sec in pool.imap_unordered(self._play_game, args): 
                    if len(winners) > 0:  # at least one player always wins, if none then game crashed 
                        total_games += 1 
                        for p in player_to_engine:
                            games[p] += 1
                        for p in winners: 
                            wins[p] += 1 
                        for p, s in enumerate(scores): 
                            totals[p] += s
                        total_time += time_sec

                        # get the names and scores for involved players
                        game_players = [player_to_engine[i] for i in range(board.n_players)]
                        player_names = [self.engines[i].name for i in game_players]
                        player_scores = [scores[i] for i in game_players]
                        winner_names = [self.engines[i].name for i in winners]
                        
                        # if there are enough players, compute elo changes
                        if board.n_players > 1:
                            player_elos = [elos[i] for i in game_players]
                            delta_elos = compute_elo_adjustment_n(player_elos, player_scores)
                            for index, player in enumerate(game_players):
                                elos[player] += delta_elos[index]
                            new_elos = [elos[i] for i in game_players]

                        match_data = MatchData(
                            board,
                            game_players,
                            player_to_engine,
                            time_sec,
                            player_elos,
                            delta_elos,
                            new_elos,
                        )
                        match_results.append(match_data)

                        # output match results
                        out_names = ' '.join([f"{i:14.14}" for i in player_names])
                        print(f"Game {total_games:>{len(str(n_games))}}: {out_names:{board.n_players * 15}}  " + 
                              f"Scores: {player_scores}  " + 
                              f"Winner(s): {', '.join(winner_names)}")
                        if verbose_board:
                            print(board)
                            print("")

                        # output rankings summary every match chunk (or minimum 10 matches)
                        if verbose_rankings and total_games % max(10, n_threads) == 0 and total_games != n_games:
                            print(get_engine_rankings())
                    else: 
                        print("Game failed to terminate")

            except KeyboardInterrupt:
                print("Caught KeyboardInterrupt, terminating workers")
                pool.terminate()

        end_time = time.time()
        results = TournamentResults(
            match_results,
            [x.name for x in self.engines],
            games,
            wins,
            totals,
            initial_elos,
            elos,
            end_time - start_time,
            total_time
        )

        if verbose_rankings:
            print("")
            print(results.get_engine_rankings_display())

        return results

    def _play_game(self, player_to_engine: list[int]) -> tuple[list[int], list[int], tilewe.Board, list[int]]:
        """
        An individual game launched by the `play` wrapper.
        Plays one game given the list of engines and returns results.

        Parameters
        ----------
        player_to_engine : list[int]
            List of engine indices indicating the players and their turn order

        Returns
        -------
        winners : list[int]
            The list of the engine indices that won the match
        scores : list[int]
            The ist of the scores earned for each engine (even those not in this match, as 0)
        board : tilewe.Board
            A reference to the game board in it's finished state
        player_to_engine : list[int]
            The list of engines that played in the match, indicating turn order
        """

        start_time = time.time()
        board = tilewe.Board(n_players=len(player_to_engine))
        try: 
            engine_to_player = { value: key for key, value in enumerate(player_to_engine) }
            while not board.finished: 
                engine = self.engines[player_to_engine[board.current_player]]
                move = engine.search(board.copy_current_state(), self.move_seconds) 
                # TODO test legality 
                board.push(move) 
            end_time = time.time()

            # put scores back in original engine order 
            winners = [ player_to_engine[x] for x in board.winners ]
            scores = [ board.scores[engine_to_player[i]] if i in engine_to_player else 0 for i in range(len(self.engines)) ]

            return winners, scores, board, player_to_engine, end_time - start_time
        
        except BaseException: 
            traceback.print_exc()
            end_time = time.time()
            return [], None, None, None, None
