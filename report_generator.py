def generate_report(result, product_type, dosage_form, indication, market):
    lines = []

    lines.append("Botanical Product Intelligence Platform")
    lines.append("Decision Report")
    lines.append("")
    lines.append("Product development question:")
    lines.append(
        f"Which medicinal plants are scientifically and commercially worth investing in "
        f"for {product_type} prepared as {dosage_form} for {indication} in {market}?"
    )
    lines.append("")
    lines.append("Results:")
    lines.append("")

    for _, row in result.iterrows():
        lines.append(f"Plant: {row.get('Scientific_Name', '')}")
        lines.append(f"Common name: {row.get('Common_Name', '')}")
        lines.append(f"Decision: {row.get('Decision_Class', '')}")
        lines.append(f"Evidence score: {row.get('Evidence_Score', '')}/100")
        lines.append(f"Commercial potential: {row.get('Commercial_Potential', '')}")
        lines.append(f"EMA status: {row.get('EMA_Status', '')}")
        lines.append(f"WHO status: {row.get('WHO_Status', '')}")
        lines.append(f"ESCOP status: {row.get('ESCOP_Status', '')}")
        lines.append(f"Clinical evidence: {row.get('Clinical_Evidence', '')}")
        lines.append(f"Infusion-specific evidence: {row.get('Infusion_Specific_Evidence', '')}")
        lines.append(f"Safety: {row.get('Safety', '')}")
        lines.append(f"Decision reason: {row.get('Decision_Reason', '')}")
        lines.append("-" * 60)

    return "\n".join(lines)
