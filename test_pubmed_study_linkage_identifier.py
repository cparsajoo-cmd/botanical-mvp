"""PubMed structured trial-registration extraction for Stage 2 linkage."""
from pubmed_connector import _parse_pubmed_xml


def test_pubmed_parser_preserves_structured_clinicaltrials_registration():
    xml = """<PubmedArticleSet><PubmedArticle><MedlineCitation>
    <PMID>12345678</PMID><Article><ArticleTitle>Trial publication</ArticleTitle>
    <Abstract><AbstractText>Results.</AbstractText></Abstract>
    <Journal><Title>Journal</Title><JournalIssue><PubDate><Year>2025</Year></PubDate></JournalIssue></Journal>
    <DataBankList><DataBank><DataBankName>ClinicalTrials.gov</DataBankName>
    <AccessionNumberList><AccessionNumber>NCT01234567</AccessionNumber></AccessionNumberList>
    </DataBank></DataBankList></Article></MedlineCitation></PubmedArticle></PubmedArticleSet>"""
    rec = _parse_pubmed_xml(xml)[0]
    assert rec["PMID"] == "12345678"
    assert rec["NCT_ID"] == "NCT01234567"
