# Test prompts for Phase 2 (same set for every model)

Use the same wording every time. End every question with /no_think.
Paste the sample document first, in the same chat, then ask the questions in order.
All names, numbers and the bank are invented.

## Sample document (about 400 words)

EXAMPLE BANK LIMITED
Account Opening Confirmation

Date of issue: 14 March 2026
Reference: AOC-2026-004417
Branch: Gulshan Branch, Dhaka

1. Account holder
Full name: Md. Rahim Uddin
Father's name: Md. Abdul Karim
Mother's name: Mst. Rokeya Begum
Date of birth: 02 August 1991
National ID number: 1991123456789
Present address: House 12, Road 5, Banani, Dhaka 1213
Occupation: Software engineer

2. Account details
Account type: Savings account
Account number: 1021-0045-77319
Currency: BDT
Opening date: 12 March 2026
Opening deposit: BDT 250,000 (two hundred fifty thousand taka only), paid by cheque number 0048213
Interest rate: 4.5 percent per year, calculated on the daily balance and paid every six months
Minimum balance: BDT 10,000

3. Services requested
The account holder requested a debit card, internet banking and SMS alerts. The debit card will be sent to the branch within ten working days. Internet banking credentials will be sent separately by post and are not shown in this letter.

4. Joint holder
A joint holder was not requested. The account will be operated by the account holder alone.

5. Charges
Annual debit card fee: BDT 1,150 including taxes. Account maintenance fee: BDT 300 every year, deducted in December. SMS alert fee: BDT 25 every quarter. A fee of BDT 500 applies if the balance falls below the minimum balance for more than ninety days.

6. Verification
The identity documents were checked by Ms. Farhana Sultana, Customer Service Officer, on 12 March 2026. The application was approved by Mr. Tanvir Ahmed, Branch Manager, on 13 March 2026. A signature card was collected and stored at the branch.

7. Contact
For questions, call the Gulshan Branch during working hours or visit the branch with this letter and a photo ID. Do not share your card number, PIN or internet banking password with anyone, including bank staff.

This is a computer-generated confirmation and is valid without a signature.

## Questions

| # | Test | Question | What a good answer says |
|---|------|----------|-------------------------|
| 1 | Short question, no document | What is the capital of Bangladesh? /no_think | Dhaka |
| 2 | One fact in the document | What was the opening deposit and on which date was the account opened? /no_think | BDT 250,000; 12 March 2026 |
| 3 | Several facts from different parts | List every person named in the document and say what role each person has. /no_think | Md. Rahim Uddin (account holder), Md. Abdul Karim (father), Mst. Rokeya Begum (mother), Ms. Farhana Sultana (checked documents), Mr. Tanvir Ahmed (approved) |
| 4 | Answer is not in the document | Who is the nominee of this account? /no_think | Says it is not stated in the document |
| 5 | Name, date and number extraction | Give the account holder's full name, date of birth, ID number and branch as a short list. /no_think | Md. Rahim Uddin; 02 August 1991; 1991123456789; Gulshan Branch |
| 6 | Follow-up that depends on the last answer | Now write the same information in one sentence. /no_think | One sentence with the same four facts |

Optional 7: paste any article of about 2,000 words and ask for a three-line summary. This tests slow reading of long text. Note how long the first word takes.

## Results (fill in for each model)

Model: ____________  Threads: ____  Context: ____  Date: ______

| # | Time to first word (s) | Total time (s) | Tokens/s shown | Correct? (yes / partly / no) | Notes |
|---|------------------------|----------------|----------------|------------------------------|-------|
| 1 | | | | | |
| 2 | | | | | |
| 3 | | | | | |
| 4 | | | | | |
| 5 | | | | | |
| 6 | | | | | |

Peak RAM during the test (Task Manager, Performance, Memory): ______ GB
Did the model admit "not stated" in test 4? yes / no
