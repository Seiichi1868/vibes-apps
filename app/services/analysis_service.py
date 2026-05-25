from app.utils.text_utils import calculate_similarity


class AnalysisService:
    @staticmethod
    def analyze_pronunciation(expected_text: str, actual_text: str, language_code: str = "ja-JP"):
        similarity = calculate_similarity(expected_text, actual_text)

        if similarity >= 90:
            evaluation = "excellent"
            message = "素晴らしい発音です！"
        elif similarity >= 70:
            evaluation = "good"
            message = "良い発音です。もう少し正確に読んでみましょう。"
        elif similarity >= 50:
            evaluation = "fair"
            message = "もう少し練習が必要です。ゆっくり丁寧に読んでみましょう。"
        else:
            evaluation = "needs_improvement"
            message = "もっと練習しましょう。お手本の音声を聞いて真似してみてください。"

        return {
            "similarity": round(similarity, 2),
            "evaluation": evaluation,
            "message": message,
            "expected_text": expected_text,
            "actual_text": actual_text,
            "language": language_code,
        }
