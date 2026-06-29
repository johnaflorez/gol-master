class ScoreCalculator:
    WINNER_POINTS = 2
    EXACT_SCORE_POINTS = 3
    PENALTY_WINNER_POINTS = 3

    def calculate(self, prediction, match):
        if match.home_score is None or match.away_score is None:
            return 0

        points = 0
        if self._correct_winner(prediction, match):
            points += self.WINNER_POINTS

        if self._exact_score(prediction, match):
            points += self.EXACT_SCORE_POINTS

        if self._correct_penalty_winner(prediction, match):
            points += self.PENALTY_WINNER_POINTS

        return points

    def _correct_winner(self, prediction, match):
        real_diff = match.home_score - match.away_score
        pred_diff = (
                prediction.predicted_home_score -
                prediction.predicted_away_score
        )
        return (real_diff == 0 and pred_diff == 0) or \
            (real_diff > 0 and pred_diff > 0) or \
            (real_diff < 0 and pred_diff < 0)

    def _exact_score(self, prediction, match):
        return (
                prediction.predicted_home_score == match.home_score and
                prediction.predicted_away_score == match.away_score
        )

    def _correct_penalty_winner(self, prediction, match):
        if match.phase not in prediction.KNOCKOUT_PHASES_WITH_PENALTIES:
            return False
        if not prediction.predicts_draw or match.home_score != match.away_score:
            return False
        if not prediction.predicted_penalty_winner or not match.winner_side:
            return False

        predicted_side = "home" if prediction.predicted_penalty_winner == prediction.PENALTY_HOME else "away"
        return predicted_side == match.winner_side

