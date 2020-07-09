#!/usr/bin/env python
# -*- coding: utf-8 -*-


# import needed libraries
import os
import pandas as pd  # type: ignore

from pandas import errors
from typing import Dict, List, Optional

from omop2obo.utils import column_splitter, data_frame_subsetter, data_frame_supersetter, merge_dictionaries


class ConceptAnnotator(object):
    """An annotator to map clinical codes to ontology terms. This workflow consists of four steps that are performed
    on data from a single clinical domain:
        1 - UMLS CUI and Semantic Type Annotation
        2 - Ontology DbXRef Mapping
        3 - Exact String Mapping to concept labels and/or synonyms
        4 - Similarity distance mapping

    Attributes:
        clinical_data: A Pandas DataFrame containing clinical data.
        ontology_dictionary: A nested dictionary containing ontology data, where outer keys are ontology identifiers
            (e.g. "hp", "mondo"), inner keys are data types (e.g. "label", "definition", "dbxref", and "synonyms").
            For each inner key, there is a third dictionary keyed by a string of that item type and with values that
            are the ontology URI for that string type.
        primary_key: A string containing the column name of the primary key.
        concept_codes: A list of column names containing concept-level codes (optional).
        concept_strings: A list of column names containing concept-level labels and synonyms (optional).
        ancestor_codes: A list of column names containing ancestor concept-level codes (optional).
        ancestor_strings: A list of column names containing ancestor concept-level labels and synonyms (optional).
        umls_cui_data: A Pandas DataFrame containing UMLS CUI data from MRCONSO.RRF.
        umls_tui_data: A Pandas DataFrame containing UMLS CUI data from MRSTY.RRF.

    Raises:
        TypeError:
            If clinical_file is not type str or if clinical_file is empty.
            If ontology_dictionary is not type dict.
            If umls_mrconso_file is not type str or if umls_mrconso_file is empty.
            If umls_mrsty_file is not type str or if umls_mrsty_file is empty.
            if primary_key is not type str.
            if concept_codes, concept_strings, ancestor_codes, and ancestor_strings (if provided) are not type list.
        OSError:
            If the clinical_file does not exist.
            If umls_mrconso_file does not exist.
            If umls_mrsty_file does not exist.
    """

    def __init__(self, clinical_file: str, ontology_dictionary: Dict, primary_key: str, concept_codes: List,
                 concept_strings: List = None, ancestor_codes: List = None, ancestor_strings: List = None,
                 umls_mrconso_file: str = None, umls_mrsty_file: str = None) -> None:

        # clinical_file
        if not isinstance(clinical_file, str):
            raise TypeError('clinical_file must be type str.')
        elif not os.path.exists(clinical_file):
            raise OSError('The {} file does not exist!'.format(clinical_file))
        elif os.stat(clinical_file).st_size == 0:
            raise TypeError('Input file: {} is empty'.format(clinical_file))
        else:
            print('**Loading {} **'.format(clinical_file))
            try:
                self.clinical_data: pd.DataFrame = pd.read_csv(clinical_file, header=0, low_memory=False).astype(str)
            except pd.errors.ParserError:
                self.clinical_data = pd.read_csv(clinical_file, header=0, sep='\t', low_memory=False).astype(str)

        # check primary key
        if not isinstance(primary_key, str): raise TypeError('primary_key must be type str.')
        else: self.primary_key: str = primary_key

        # check for concept-level information
        if not isinstance(concept_codes, List): raise TypeError('concept_codes must be type list.')
        else: self.concept_codes: List = concept_codes

        # check concept-level string input (optional)
        if not concept_strings:
            self.concept_strings: Optional[List] = concept_strings
        else:
            if not isinstance(concept_strings, List): raise TypeError('concept_strings must be type list.')
            else: self.concept_strings = concept_strings

        # check ancestor-level codes input (optional)
        if not ancestor_codes:
            self.ancestor_codes: Optional[List] = ancestor_codes
        else:
            if not isinstance(ancestor_codes, List): raise TypeError('ancestor_codes must be type list.')
            else: self.ancestor_codes = ancestor_codes

        # check ancestor-level strings input (optional)
        if not ancestor_strings:
            self.ancestor_strings = ancestor_strings
        else:
            if not isinstance(ancestor_strings, List): raise TypeError('ancestor_strings must be type list.')
            else: self.ancestor_strings = ancestor_strings

        # check ontology_dictionary
        if not isinstance(ontology_dictionary, Dict): raise TypeError('ontology_dictionary must be type dict.')
        else: self.ontology_dictionary: Dict = ontology_dictionary

        # check for UMLS MRCONSO file
        if not umls_mrconso_file: self.umls_data: Optional[pd.DataFrame] = None
        else:
            if not isinstance(umls_mrconso_file, str):
                raise TypeError('umls_mrconso_file must be type str.')
            elif not os.path.exists(umls_mrconso_file):
                raise OSError('The {} file does not exist!'.format(umls_mrconso_file))
            elif os.stat(umls_mrconso_file).st_size == 0:
                raise TypeError('Input file: {} is empty'.format(umls_mrconso_file))
            else:
                print('**Loading UMLS MRCONSO Data **')
                headers = ['CUI', 'SAB', 'CODE']
                self.umls_cui_data = pd.read_csv(umls_mrconso_file, header=None, sep='|', names=headers,
                                                 low_memory=False, usecols=[0, 11, 13]).drop_duplicates().astype(str)
                self.umls_cui_data = self.umls_cui_data[self.umls_cui_data.CODE != 'NOCODE'].drop_duplicates()

        # check for UMLS MRSTY file
        if not umls_mrsty_file: self.umls_tui_data: Optional[pd.DataFrame] = None
        else:
            if not isinstance(umls_mrsty_file, str):
                raise TypeError('umls_mrsty_file must be type str.')
            elif not os.path.exists(umls_mrsty_file):
                raise OSError('The {} file does not exist!'.format(umls_mrsty_file))
            elif os.stat(umls_mrsty_file).st_size == 0:
                raise TypeError('Input file: {} is empty'.format(umls_mrsty_file))
            else:
                print('**Loading UMLS MRSTY Data **')
                headers = ['CUI', 'STY']
                self.umls_tui_data = pd.read_csv(umls_mrsty_file, header=None, sep='|', names=headers,
                                                 low_memory=False, usecols=[0, 3]).drop_duplicates().astype(str)

    def umls_cui_annotator(self, primary_key: str, code_level: str) -> pd.DataFrame:
        """Method maps concepts in a clinical data file to UMLS concepts and semantic types from the umls_cui_data
        and umls_tui_data Pandas Data Frames.

        Args:
            primary_key: A string containing the name of the primary key (i.e. CONCEPT_ID).
            code_level: A string containing the name of the source code column (i.e. CONCEPT_SOURCE_CODE).

        Returns:
           umls_cui_semtype: A Pandas DataFrame containing clinical concept ids and source codes as well as UMLS
            CUIs, source codes, and semantic types.
        """

        # reduce data to only those columns needed for merging
        clinical_ids = self.clinical_data[[primary_key, code_level]].drop_duplicates()

        # merge reduced clinical concepts with umls concepts
        umls_cui = clinical_ids.merge(self.umls_cui_data, how='inner', left_on=code_level, right_on='CODE')
        umls_cui_semtype = umls_cui.merge(self.umls_tui_data, how='left', on='CUI').drop_duplicates()

        # update column names
        updated_cols = [primary_key, code_level, 'UMLS_CUI', 'UMLS_SAB', 'UMLS_CODE', 'UMLS_SEM_TYPE']
        umls_cui_semtype.columns = updated_cols

        return umls_cui_semtype

    def dbxref_mapper(self, data: pd.DataFrame) -> pd.DataFrame:
        """Takes a stacked Pandas DataFrame and merges it with a Pandas DataFrame version of the
        ontology_dictionary_object.

        Args:
            data: A stacked Pandas DataFrame containing output from the umls_cui_annotator method.

        Returns:
            merged_dbxrefs: A stacked
        """

        # prepare ontology data
        combined_dictionaries = merge_dictionaries(self.ontology_dictionary, 'dbxref')
        combo_dict_df = pd.DataFrame(combined_dictionaries.items(), columns=['DBXREF', 'ONT_URI'])
        combo_dict_df['CODE'] = combo_dict_df['DBXREF'].apply(lambda x: x.split(':')[-1])

        # merge clinical data and combined ontology dict
        merged_dbxrefs = data.merge(combo_dict_df, how='inner', on='CODE').drop_duplicates()
        merged_dbxrefs['ONT'] = merged_dbxrefs['ONT_URI'].apply(lambda x: x.split('/')[-1].split('_')[0].upper())
        merged_dbxrefs['EVIDENCE'] = merged_dbxrefs['DBXREF'].apply(lambda x: 'DbXRef_' + x.split(':')[0])

        return merged_dbxrefs.drop_duplicates()

    # def concept_string_match(self, data: pd.DataFrame, string_columns: str) -> pd.DataFrame:

    # def clinical_concept_mapper(self, primary_key: str, code_level: str):
    #     """
    #
    #     Args:
    #         primary_key:
    #         code_level:
    #
    #     Returns:
    #
    #     """
    #
    #     # TODO: figure out how to do this for both concept and concept_ancestor, maybe this is done in main
    #     if self.ancestor_codes is not None:
    #         mapping_levels = {'concepts': {'codes': self.concept_codes, 'strings': self.concept_strings},
    #                           'ancestors': {'codes': self.ancestor_codes, 'strings': self.ancestor_strings}}
    #     else:
    #         mapping_levels = {'concepts': {'codes': self.concept_codes, 'strings': self.concept_strings}}
    #
    #     for concept_key in mapping_levels.keys():
    #         print('\n\n #### ANNOTATING {}.upper()'.format(concept_key))
    #
    #         primary_key = self.primary_key
    #         code_level = mapping_levels[concept_key]['codes'][0]
    #         code_strings = mapping_levels[concept_key]['strings']
    #
    #         # STEP 1: UMLS CUI + SEMANTIC TYPE ANNOTATION
    #         print('\n*** STEP 1: Performing UMLS CUI + Semantic Type Annotation ***')
    #         if self.umls_cui_data and self.umls_tui_data:
    #             umls_annotations = self.umls_cui_annotator(primary_key, code_level)
    #             subset = [code_level, 'UMLS_CODE', 'UMLS_CUI']
    #             data_stacked = data_frame_subsetter(umls_annotations[[primary_key] + subset], primary_key, subset)
    #         else:
    #             print('Did not provide MRCONSO and MRSTY Files -- Skipping UMLS Annotation Step')
    #             clinical_subset = self.clinical_data[[primary_key, code_level]]
    #             data_stacked = data_frame_subsetter(clinical_subset, primary_key, [code_level])
    #
    #         # STEP 2 - DBXREF ANNOTATION
    #         print('\n*** STEP 2: Performing DbXRef Annotation ***')
    #         stacked_dbxref = self.dbxref_mapper(data_stacked)
    #
    #         # STEP 3 - EXACT STRING MAPPING
    #         print('\n*** STEP 3: Performing Exact String Mapping ***')
    #         clinical_strings = self.clinical_data.copy()
    #         clinical_strings = clinical_strings[[primary_key] + code_strings]
    #
    #         # unstack "|" delimited data
    #         string_columns = ['CONCEPT_LABEL', 'CONCEPT_SYNONYM']
    #         split_strings = column_splitter(clinical_strings, string_columns, '|')
    #
    #         # find exact string matches
    #
    #         # aggregate umls, dbxref, string mapping
    #
    #         # add concepts to concept list
    #
    #     # combine concept and ancestor-level results
    #
    #     return None
