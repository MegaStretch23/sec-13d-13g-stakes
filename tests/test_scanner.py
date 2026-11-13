import unittest
from sec_13d_13g_stakes.scanner import parse_index, parse_xml, purpose_flags

FIX_13D = b"""<?xml version="1.0" encoding="UTF-8"?><edgarSubmission xmlns="http://www.sec.gov/edgar/schedule13d" xmlns:com="http://www.sec.gov/edgar/common">
<headerData><submissionType>SCHEDULE 13D</submissionType><filerInfo><filer><filerCredentials><cik>0001000267</cik></filerCredentials></filer></filerInfo></headerData>
<formData><coverPageHeader><securitiesClassTitle>Common Stock, par value $0.01 per share</securitiesClassTitle><dateOfEvent>09/18/2026</dateOfEvent>
<issuerInfo><issuerCIK>0001234567</issuerCIK><issuerName>URSB Bancorp, Inc.</issuerName><issuerCusips><issuerCusipNumber>90323M102</issuerCusipNumber></issuerCusips></issuerInfo>
<reportingPersons><reportingPersonInfo><reportingPersonCIK>0001000267</reportingPersonCIK><reportingPersonName>SEIDMAN &amp; ASSOCIATES LLC</reportingPersonName><fundType>WC</fundType>
<citizenshipOrOrganization>NJ</citizenshipOrOrganization><soleVotingPower>51642.00</soleVotingPower><sharedVotingPower>0.00</sharedVotingPower><soleDispositivePower>51642.00</soleDispositivePower>
<sharedDispositivePower>0.00</sharedDispositivePower><aggregateAmountOwned>51642.00</aggregateAmountOwned><percentOfClass>2.2</percentOfClass><typeOfReportingPerson>OO</typeOfReportingPerson></reportingPersonInfo>
<reportingPersonInfo><reportingPersonName>LAWRENCE B. SEIDMAN</reportingPersonName><citizenshipOrOrganization>United States</citizenshipOrOrganization><aggregateAmountOwned>209,940.00</aggregateAmountOwned>
<percentOfClass>9.0</percentOfClass><typeOfReportingPerson>IN</typeOfReportingPerson></reportingPersonInfo></reportingPersons></coverPageHeader>
<items1To7><item3><fundsSource>The Shares were purchased with working capital.</fundsSource></item3>
<item4><transactionPurpose>The Reporting Persons believe the Shares are undervalued. They intend to engage in discussions with the Board of Directors regarding strategic alternatives, including a sale of the Company.</transactionPurpose></item4></items1To7>
</formData></edgarSubmission>"""
FIX_13G = b"""<?xml version="1.0" encoding="UTF-8"?><edgarSubmission xmlns="http://www.sec.gov/edgar/schedule13g" xmlns:com="http://www.sec.gov/edgar/common">
<headerData><submissionType>SCHEDULE 13G</submissionType></headerData><formData><coverPageHeader><securitiesClassTitle>Common Shares</securitiesClassTitle>
<issuerInfo><issuerCik>0000821130</issuerCik><issuerName>ARRAY DIGITAL INFRASTRUCTURE, INC.</issuerName><issuerCusips><issuerCusipNumber>04271T100</issuerCusipNumber></issuerCusips></issuerInfo>
<eventDateRequiresFilingThisStatement>09/15/2026</eventDateRequiresFilingThisStatement>
<coverPageHeaderReportingPersonDetails><reportingPersonName>BIG INDEX ADVISERS LLC</reportingPersonName><typeOfReportingPerson>IA</typeOfReportingPerson><classPercent>6.1</classPercent>
<reportingPersonBeneficiallyOwnedAggregateNumberOfShares>5,300,000</reportingPersonBeneficiallyOwnedAggregateNumberOfShares><soleVotingPower>5000000</soleVotingPower><sharedVotingPower>0</sharedVotingPower>
<soleDispositivePower>5300000</soleDispositivePower><sharedDispositivePower>0</sharedDispositivePower><citizenshipOrOrganization>DE</citizenshipOrOrganization></coverPageHeaderReportingPersonDetails>
</coverPageHeader></formData></edgarSubmission>"""
FIX_IDX = """Description: Daily Index of EDGAR Dissemination Feed by Form Type
---------------------------------------------------------------------------
SCHEDULE 13D     SEIDMAN LAWRENCE B                                            1026081     20260923    edgar/data/1026081/0000921895-26-002628.txt
SCHEDULE 13D/A   SOME FUND LP                                                  2222222     20260923    edgar/data/2222222/0000921895-26-002629.txt
SCHEDULE 13G     ARRAY DIGITAL INFRASTRUCTURE, INC.                            821130      20260923    edgar/data/821130/0001609074-26-000001.txt
SC 13G/A         LEGACY HTML FILER                                             3333333     20260923    edgar/data/3333333/0000000000-26-000001.txt
8-K              EXAMPLE CORP                                                  1234567     20260923    edgar/data/1234567/0001234567-26-000123.txt
"""


class T(unittest.TestCase):
    def test_index(self):
        rows, legacy = parse_index(FIX_IDX)
        self.assertEqual([r["form"] for r in rows], ["SCHEDULE 13D", "SCHEDULE 13D/A", "SCHEDULE 13G"])
        self.assertEqual(legacy, 1)
        self.assertEqual(rows[0]["xml_url"], "https://www.sec.gov/Archives/edgar/data/1026081/000092189526002628/primary_doc.xml")
        self.assertEqual([r["form"] for r in parse_index(FIX_IDX, include_amendments=False)[0]], ["SCHEDULE 13D", "SCHEDULE 13G"])
        self.assertEqual([r["form"] for r in parse_index(FIX_IDX, schedules={"13D"})[0]], ["SCHEDULE 13D", "SCHEDULE 13D/A"])

    def test_same_filing_listed_twice_is_kept_once(self):
        from unittest import mock
        from sec_13d_13g_stakes import scanner
        dup = FIX_IDX + FIX_IDX.splitlines()[2].replace("SEIDMAN LAWRENCE B   ", "URSB BANCORP INC      ").replace("1026081", "1234567") + "\n"
        with mock.patch.object(scanner, "fetch_daily", return_value=scanner.parse_index(dup)):
            rows, _ = scanner.collect_window(None, __import__("datetime").date(2026, 9, 23), 1)
        self.assertEqual(len(rows), len({r["accession"] for r in rows}))
        self.assertEqual(len(rows), 3)

    def test_13d(self):
        d = parse_xml(FIX_13D)
        self.assertEqual((d["schedule"], d["issuerName"], d["cusip"], d["eventDate"]), ("13D", "URSB Bancorp, Inc.", "90323M102", "2026-09-18"))
        self.assertEqual(d["personCount"], 2)
        self.assertEqual(d["reportingPersons"][1]["aggregateShares"], 209940.0)
        self.assertEqual(d["maxPercentOfClass"], 9.0)
        self.assertEqual(d["purposeFlags"], ["board", "strategic-alternatives", "engage"])

    def test_13g(self):
        g = parse_xml(FIX_13G)
        self.assertEqual((g["schedule"], g["eventDate"], g["personCount"]), ("13G", "2026-09-15", 1))
        self.assertEqual(g["reportingPersons"][0]["type"], "investment adviser")
        self.assertEqual(g["reportingPersons"][0]["aggregateShares"], 5300000.0)
        self.assertIsNone(g["purposeOfTransaction"])

    def test_bad_values_are_null_not_guessed(self):
        bad = parse_xml(FIX_13D.replace(b"<percentOfClass>9.0</percentOfClass>", b"<percentOfClass>n/a</percentOfClass>")
                        .replace(b"<dateOfEvent>09/18/2026</dateOfEvent>", b"<dateOfEvent>soon</dateOfEvent>"))
        self.assertIsNone(bad["reportingPersons"][1]["percentOfClass"])
        self.assertEqual(bad["maxPercentOfClass"], 2.2)
        self.assertIsNone(bad["eventDate"])

    def test_flags(self):
        self.assertEqual(purpose_flags("intends to acquire the remaining shares by tender offer and seek a merger"), ["merger"])


if __name__ == "__main__":
    unittest.main()
