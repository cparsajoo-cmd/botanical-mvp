from dataclasses import dataclass
import pandas as pd


@dataclass
class MarketResult:

    scientific_name: str

    common_name: str

    market_category: str

    market_score: float

    estimated_products: int

    commercial_maturity: str

    recommendation: str

    notes: str


class MarketIntelligenceEngine:

    """
    Commercial Intelligence Engine

    Determines whether a plant already has
    a commercial ecosystem or represents
    a white-space opportunity.
    """

    def evaluate(self, row):

        score = 0

        products = 0

        notes = []

        #############################
        # EMA
        #############################

        if row.get("ema", False):

            score += 20
            notes.append("EMA accepted")

        #############################
        # WHO
        #############################

        if row.get("who", False):

            score += 10
            notes.append("WHO monograph")

        #############################
        # ESCOP
        #############################

        if row.get("escop", False):

            score += 10
            notes.append("ESCOP")

        #############################
        # Clinical
        #############################

        clinical = row.get("clinical_trials", 0)

        if clinical > 20:

            score += 20

        elif clinical > 5:

            score += 12

        elif clinical > 0:

            score += 5

        #############################
        # Products
        #############################

        marketed = row.get("market_products", 0)

        products += marketed

        if marketed > 100:

            score += 30

        elif marketed > 30:

            score += 20

        elif marketed > 10:

            score += 12

        elif marketed > 0:

            score += 5

        #############################
        # Patents
        #############################

        patents = row.get("patents", 0)

        if patents > 200:

            score += 10

        elif patents > 20:

            score += 6

        #############################

        if score >= 80:

            maturity = "Established Global Market"

        elif score >= 60:

            maturity = "Strong Commercial Market"

        elif score >= 40:

            maturity = "Growing Market"

        elif score >= 20:

            maturity = "Emerging Market"

        else:

            maturity = "Very Early Market"

        #################################

        if score >= 70:

            category = "Commercial"

            recommendation = "Compete or Differentiate"

        elif score >= 40:

            category = "Commercial + Innovation"

            recommendation = "Look for market gaps"

        else:

            category = "Innovation"

            recommendation = "White-space opportunity"

        #################################

        return MarketResult(

            scientific_name=row["Scientific_Name"],

            common_name=row["Common_Name"],

            market_category=category,

            market_score=round(score, 1),

            estimated_products=products,

            commercial_maturity=maturity,

            recommendation=recommendation,

            notes=", ".join(notes)

        )
