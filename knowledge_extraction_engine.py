from dataclasses import dataclass
from typing import List
import re


@dataclass
class KnowledgeRecord:

    plant:str=""
    compound:str=""
    target:str=""
    mechanism:str=""
    pathway:str=""
    indication:str=""
    disease:str=""
    evidence_type:str=""
    species:str=""
    dose:str=""
    safety:str=""
    source:str=""
    confidence:float=0.0


class KnowledgeExtractionEngine:

    def __init__(self):
        pass


    def extract(self,paper):

        text=str(paper)

        record=KnowledgeRecord()

        record.plant=self.extract_plant(text)

        record.compound=self.extract_compound(text)

        record.target=self.extract_target(text)

        record.mechanism=self.extract_mechanism(text)

        record.pathway=self.extract_pathway(text)

        record.indication=self.extract_indication(text)

        record.disease=self.extract_disease(text)

        record.species=self.extract_species(text)

        record.evidence_type=self.extract_evidence(text)

        record.source="PubMed"

        record.confidence=self.calculate_confidence(record)

        return record


    def extract_plant(self,text):

        return ""


    def extract_compound(self,text):

        return ""


    def extract_target(self,text):

        return ""


    def extract_mechanism(self,text):

        return ""


    def extract_pathway(self,text):

        return ""


    def extract_indication(self,text):

        return ""


    def extract_disease(self,text):

        return ""


    def extract_species(self,text):

        return ""


    def extract_evidence(self,text):

        return ""


    def calculate_confidence(self,record):

        score=0

        if record.plant!="":
            score+=10

        if record.compound!="":
            score+=15

        if record.target!="":
            score+=20

        if record.mechanism!="":
            score+=20

        if record.pathway!="":
            score+=15

        if record.indication!="":
            score+=10

        if record.disease!="":
            score+=10

        return score
