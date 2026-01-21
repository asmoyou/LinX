"""User satisfaction metrics.

References:
- Requirements 11: Monitoring and Analytics
- Design Section 24.2: Business Metrics
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from enum import Enum
from uuid import UUID, uuid4
import statistics

logger = logging.getLogger(__name__)


class SatisfactionRating(Enum):
    """Satisfaction rating levels."""
    
    VERY_DISSATISFIED = 1
    DISSATISFIED = 2
    NEUTRAL = 3
    SATISFIED = 4
    VERY_SATISFIED = 5


@dataclass
class SatisfactionSurvey:
    """User satisfaction survey response."""
    
    survey_id: UUID
    user_id: UUID
    submitted_at: datetime
    
    # Ratings
    overall_rating: SatisfactionRating
    ease_of_use: Optional[SatisfactionRating] = None
    response_quality: Optional[SatisfactionRating] = None
    response_speed: Optional[SatisfactionRating] = None
    reliability: Optional[SatisfactionRating] = None
    
    # Feedback
    feedback_text: Optional[str] = None
    would_recommend: Optional[bool] = None
    
    # Context
    task_id: Optional[UUID] = None
    agent_id: Optional[UUID] = None
    
    def get_average_rating(self) -> float:
        """Calculate average rating across all dimensions.
        
        Returns:
            Average rating (1-5)
        """
        ratings = [
            self.overall_rating.value,
            self.ease_of_use.value if self.ease_of_use else None,
            self.response_quality.value if self.response_quality else None,
            self.response_speed.value if self.response_speed else None,
            self.reliability.value if self.reliability else None,
        ]
        
        valid_ratings = [r for r in ratings if r is not None]
        
        if valid_ratings:
            return statistics.mean(valid_ratings)
        return 0.0


@dataclass
class SatisfactionMetrics:
    """Satisfaction metrics for a time period."""
    
    period_start: datetime
    period_end: datetime
    
    # Survey metrics
    total_surveys: int = 0
    response_rate: float = 0.0
    
    # Ratings
    avg_overall_rating: float = 0.0
    avg_ease_of_use: float = 0.0
    avg_response_quality: float = 0.0
    avg_response_speed: float = 0.0
    avg_reliability: float = 0.0
    
    # NPS (Net Promoter Score)
    nps_score: float = 0.0
    promoters_percent: float = 0.0
    passives_percent: float = 0.0
    detractors_percent: float = 0.0
    
    # Sentiment
    positive_feedback_percent: float = 0.0
    neutral_feedback_percent: float = 0.0
    negative_feedback_percent: float = 0.0
    
    # Trends
    trend_direction: str = "stable"  # improving, declining, stable


class SatisfactionTracker:
    """User satisfaction tracking system.
    
    Tracks and analyzes:
    - Survey responses
    - User ratings
    - Net Promoter Score (NPS)
    - Feedback sentiment
    - Satisfaction trends
    """
    
    def __init__(self, database=None):
        """Initialize satisfaction tracker.
        
        Args:
            database: Database connection
        """
        self.database = database
        self.surveys: List[SatisfactionSurvey] = []
        
        logger.info("SatisfactionTracker initialized")
    
    def submit_survey(
        self,
        user_id: UUID,
        overall_rating: SatisfactionRating,
        ease_of_use: Optional[SatisfactionRating] = None,
        response_quality: Optional[SatisfactionRating] = None,
        response_speed: Optional[SatisfactionRating] = None,
        reliability: Optional[SatisfactionRating] = None,
        feedback_text: Optional[str] = None,
        would_recommend: Optional[bool] = None,
        task_id: Optional[UUID] = None,
        agent_id: Optional[UUID] = None,
    ) -> SatisfactionSurvey:
        """Submit a satisfaction survey.
        
        Args:
            user_id: User ID
            overall_rating: Overall satisfaction rating
            ease_of_use: Ease of use rating
            response_quality: Response quality rating
            response_speed: Response speed rating
            reliability: Reliability rating
            feedback_text: Optional feedback text
            would_recommend: Would recommend to others
            task_id: Optional task ID
            agent_id: Optional agent ID
            
        Returns:
            SatisfactionSurvey
        """
        survey = SatisfactionSurvey(
            survey_id=uuid4(),
            user_id=user_id,
            submitted_at=datetime.now(),
            overall_rating=overall_rating,
            ease_of_use=ease_of_use,
            response_quality=response_quality,
            response_speed=response_speed,
            reliability=reliability,
            feedback_text=feedback_text,
            would_recommend=would_recommend,
            task_id=task_id,
            agent_id=agent_id,
        )
        
        self.surveys.append(survey)
        logger.info(f"Survey submitted: {survey.survey_id}")
        
        return survey
    
    def calculate_metrics(
        self,
        start_date: datetime,
        end_date: datetime,
        user_id: Optional[UUID] = None,
        agent_id: Optional[UUID] = None,
    ) -> SatisfactionMetrics:
        """Calculate satisfaction metrics.
        
        Args:
            start_date: Start date
            end_date: End date
            user_id: Optional user ID filter
            agent_id: Optional agent ID filter
            
        Returns:
            SatisfactionMetrics
        """
        logger.info(f"Calculating satisfaction metrics from {start_date} to {end_date}")
        
        # Filter surveys
        filtered_surveys = [
            s for s in self.surveys
            if start_date <= s.submitted_at <= end_date
        ]
        
        if user_id:
            filtered_surveys = [s for s in filtered_surveys if s.user_id == user_id]
        
        if agent_id:
            filtered_surveys = [s for s in filtered_surveys if s.agent_id == agent_id]
        
        metrics = SatisfactionMetrics(
            period_start=start_date,
            period_end=end_date,
        )
        
        if not filtered_surveys:
            return metrics
        
        metrics.total_surveys = len(filtered_surveys)
        
        # Calculate average ratings
        overall_ratings = [s.overall_rating.value for s in filtered_surveys]
        metrics.avg_overall_rating = statistics.mean(overall_ratings)
        
        ease_ratings = [s.ease_of_use.value for s in filtered_surveys if s.ease_of_use]
        if ease_ratings:
            metrics.avg_ease_of_use = statistics.mean(ease_ratings)
        
        quality_ratings = [s.response_quality.value for s in filtered_surveys if s.response_quality]
        if quality_ratings:
            metrics.avg_response_quality = statistics.mean(quality_ratings)
        
        speed_ratings = [s.response_speed.value for s in filtered_surveys if s.response_speed]
        if speed_ratings:
            metrics.avg_response_speed = statistics.mean(speed_ratings)
        
        reliability_ratings = [s.reliability.value for s in filtered_surveys if s.reliability]
        if reliability_ratings:
            metrics.avg_reliability = statistics.mean(reliability_ratings)
        
        # Calculate NPS
        nps_data = self._calculate_nps(filtered_surveys)
        metrics.nps_score = nps_data["nps_score"]
        metrics.promoters_percent = nps_data["promoters_percent"]
        metrics.passives_percent = nps_data["passives_percent"]
        metrics.detractors_percent = nps_data["detractors_percent"]
        
        # Analyze sentiment
        sentiment_data = self._analyze_sentiment(filtered_surveys)
        metrics.positive_feedback_percent = sentiment_data["positive_percent"]
        metrics.neutral_feedback_percent = sentiment_data["neutral_percent"]
        metrics.negative_feedback_percent = sentiment_data["negative_percent"]
        
        # Determine trend
        metrics.trend_direction = self._determine_trend(start_date, end_date)
        
        return metrics
    
    def _calculate_nps(
        self,
        surveys: List[SatisfactionSurvey],
    ) -> Dict[str, float]:
        """Calculate Net Promoter Score.
        
        NPS is based on the question "Would you recommend this to others?"
        - Promoters: rating 9-10 (or would_recommend=True + high rating)
        - Passives: rating 7-8
        - Detractors: rating 0-6 (or would_recommend=False)
        
        NPS = % Promoters - % Detractors
        
        Args:
            surveys: List of surveys
            
        Returns:
            Dictionary with NPS data
        """
        if not surveys:
            return {
                "nps_score": 0.0,
                "promoters_percent": 0.0,
                "passives_percent": 0.0,
                "detractors_percent": 0.0,
            }
        
        promoters = 0
        passives = 0
        detractors = 0
        
        for survey in surveys:
            # Use overall rating as proxy for NPS
            rating = survey.overall_rating.value
            
            if rating >= 4.5:  # Very satisfied
                promoters += 1
            elif rating >= 3.5:  # Satisfied
                passives += 1
            else:  # Neutral or dissatisfied
                detractors += 1
        
        total = len(surveys)
        promoters_percent = (promoters / total * 100) if total > 0 else 0
        passives_percent = (passives / total * 100) if total > 0 else 0
        detractors_percent = (detractors / total * 100) if total > 0 else 0
        
        nps_score = promoters_percent - detractors_percent
        
        return {
            "nps_score": nps_score,
            "promoters_percent": promoters_percent,
            "passives_percent": passives_percent,
            "detractors_percent": detractors_percent,
        }
    
    def _analyze_sentiment(
        self,
        surveys: List[SatisfactionSurvey],
    ) -> Dict[str, float]:
        """Analyze feedback sentiment.
        
        Args:
            surveys: List of surveys
            
        Returns:
            Dictionary with sentiment percentages
        """
        if not surveys:
            return {
                "positive_percent": 0.0,
                "neutral_percent": 0.0,
                "negative_percent": 0.0,
            }
        
        positive = 0
        neutral = 0
        negative = 0
        
        for survey in surveys:
            # Simple sentiment based on overall rating
            rating = survey.overall_rating.value
            
            if rating >= 4:
                positive += 1
            elif rating >= 3:
                neutral += 1
            else:
                negative += 1
        
        total = len(surveys)
        
        return {
            "positive_percent": (positive / total * 100) if total > 0 else 0,
            "neutral_percent": (neutral / total * 100) if total > 0 else 0,
            "negative_percent": (negative / total * 100) if total > 0 else 0,
        }
    
    def _determine_trend(
        self,
        start_date: datetime,
        end_date: datetime,
    ) -> str:
        """Determine satisfaction trend.
        
        Args:
            start_date: Start date
            end_date: End date
            
        Returns:
            Trend direction: improving, declining, stable
        """
        # Compare with previous period
        period_days = (end_date - start_date).days
        previous_end = start_date
        previous_start = previous_end - timedelta(days=period_days)
        
        # Filter surveys for current period
        current_surveys = [
            s for s in self.surveys
            if start_date <= s.submitted_at <= end_date
        ]
        
        # Filter surveys for previous period
        previous_surveys = [
            s for s in self.surveys
            if previous_start <= s.submitted_at <= previous_end
        ]
        
        if not current_surveys or not previous_surveys:
            return "stable"
        
        # Calculate average ratings directly without calling calculate_metrics
        current_avg = statistics.mean([s.overall_rating.value for s in current_surveys])
        previous_avg = statistics.mean([s.overall_rating.value for s in previous_surveys])
        
        rating_change = current_avg - previous_avg
        
        if rating_change > 0.3:
            return "improving"
        elif rating_change < -0.3:
            return "declining"
        else:
            return "stable"
    
    def get_satisfaction_report(
        self,
        start_date: datetime,
        end_date: datetime,
    ) -> Dict[str, Any]:
        """Get comprehensive satisfaction report.
        
        Args:
            start_date: Start date
            end_date: End date
            
        Returns:
            Dictionary with satisfaction report
        """
        metrics = self.calculate_metrics(start_date, end_date)
        
        return {
            "period": {
                "start": start_date.isoformat(),
                "end": end_date.isoformat(),
                "days": (end_date - start_date).days,
            },
            "overview": {
                "total_surveys": metrics.total_surveys,
                "avg_overall_rating": metrics.avg_overall_rating,
                "nps_score": metrics.nps_score,
                "trend": metrics.trend_direction,
            },
            "ratings": {
                "overall": metrics.avg_overall_rating,
                "ease_of_use": metrics.avg_ease_of_use,
                "response_quality": metrics.avg_response_quality,
                "response_speed": metrics.avg_response_speed,
                "reliability": metrics.avg_reliability,
            },
            "nps": {
                "score": metrics.nps_score,
                "promoters_percent": metrics.promoters_percent,
                "passives_percent": metrics.passives_percent,
                "detractors_percent": metrics.detractors_percent,
            },
            "sentiment": {
                "positive_percent": metrics.positive_feedback_percent,
                "neutral_percent": metrics.neutral_feedback_percent,
                "negative_percent": metrics.negative_feedback_percent,
            },
            "insights": self._generate_insights(metrics),
        }
    
    def _generate_insights(
        self,
        metrics: SatisfactionMetrics,
    ) -> List[str]:
        """Generate insights from satisfaction metrics.
        
        Args:
            metrics: Satisfaction metrics
            
        Returns:
            List of insight strings
        """
        insights = []
        
        # Overall satisfaction insight
        if metrics.avg_overall_rating >= 4.0:
            insights.append(f"High user satisfaction with average rating of {metrics.avg_overall_rating:.1f}/5")
        elif metrics.avg_overall_rating < 3.0:
            insights.append(f"Low user satisfaction ({metrics.avg_overall_rating:.1f}/5) requires immediate attention")
        
        # NPS insight
        if metrics.nps_score >= 50:
            insights.append(f"Excellent NPS score of {metrics.nps_score:.0f} indicates strong user loyalty")
        elif metrics.nps_score < 0:
            insights.append(f"Negative NPS score ({metrics.nps_score:.0f}) indicates user dissatisfaction")
        
        # Trend insight
        if metrics.trend_direction == "improving":
            insights.append("Satisfaction is improving - continue current initiatives")
        elif metrics.trend_direction == "declining":
            insights.append("Satisfaction is declining - investigate root causes")
        
        # Specific dimension insights
        if metrics.avg_response_speed < 3.5:
            insights.append("Response speed is a concern - consider performance optimization")
        
        if metrics.avg_response_quality < 3.5:
            insights.append("Response quality needs improvement - review agent training")
        
        return insights
    
    def get_agent_satisfaction(
        self,
        agent_id: UUID,
        start_date: datetime,
        end_date: datetime,
    ) -> Dict[str, Any]:
        """Get satisfaction metrics for a specific agent.
        
        Args:
            agent_id: Agent ID
            start_date: Start date
            end_date: End date
            
        Returns:
            Dictionary with agent satisfaction data
        """
        metrics = self.calculate_metrics(start_date, end_date, agent_id=agent_id)
        
        return {
            "agent_id": str(agent_id),
            "period": {
                "start": start_date.isoformat(),
                "end": end_date.isoformat(),
            },
            "surveys_received": metrics.total_surveys,
            "avg_rating": metrics.avg_overall_rating,
            "nps_score": metrics.nps_score,
            "positive_feedback_percent": metrics.positive_feedback_percent,
        }
    
    def get_top_rated_agents(
        self,
        start_date: datetime,
        end_date: datetime,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """Get top-rated agents.
        
        Args:
            start_date: Start date
            end_date: End date
            limit: Maximum number of agents to return
            
        Returns:
            List of agent ratings
        """
        # Group surveys by agent
        agent_surveys: Dict[UUID, List[SatisfactionSurvey]] = {}
        
        for survey in self.surveys:
            if (survey.agent_id and 
                start_date <= survey.submitted_at <= end_date):
                if survey.agent_id not in agent_surveys:
                    agent_surveys[survey.agent_id] = []
                agent_surveys[survey.agent_id].append(survey)
        
        # Calculate average rating for each agent
        agent_ratings = []
        for agent_id, surveys in agent_surveys.items():
            avg_rating = statistics.mean([s.overall_rating.value for s in surveys])
            agent_ratings.append({
                "agent_id": str(agent_id),
                "avg_rating": avg_rating,
                "survey_count": len(surveys),
            })
        
        # Sort by rating
        agent_ratings.sort(key=lambda x: x["avg_rating"], reverse=True)
        
        return agent_ratings[:limit]
