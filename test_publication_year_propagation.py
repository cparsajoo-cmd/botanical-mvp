from end_to_end_validation import RetrievedEvidence
from pubmed_connector import _parse_pubmed_xml


def test_pubmed_xml_extracts_publication_year():
    xml = '''<PubmedArticleSet><PubmedArticle><MedlineCitation><PMID>123</PMID><Article><ArticleTitle>T</ArticleTitle><Journal><JournalIssue><PubDate><Year>2025</Year></PubDate></JournalIssue><Title>J</Title></Journal><Abstract><AbstractText>A</AbstractText></Abstract></Article></MedlineCitation></PubmedArticle></PubmedArticleSet>'''
    rows = _parse_pubmed_xml(xml)
    assert rows[0]['Year'] == '2025'


def test_retrieved_evidence_propagates_publication_year_to_engine_row():
    rec = RetrievedEvidence(reference_id='r', scientific_name='Plantus testus', notes='x', publication_year=2025)
    row = rec.to_engine_row('Indication', 'oral', '')
    assert row['Source_Year'] == 2025
