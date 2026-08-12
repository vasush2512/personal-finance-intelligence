"""Generate data/sample_statement.csv — a deliberately messy fake statement.

Never use a real bank statement in this repo. This file is what every test
and demo runs against.
"""

import csv
import os
import random
from datetime import date, timedelta

random.seed(7)

MERCHANTS = [
    # (narration template, rough amount range)
    ("UPI/DR/{ref}/SWIGGY/HDFC/swiggy@icici/Payment", 150, 700),
    ("UPI/DR/{ref}/ZOMATO ONLINE/AXIS/zomato@ybl/Order", 180, 900),
    ("UPI/DR/{ref}/DOMINOS PIZZA/ICICI/dominos@okhdfcbank/Pay", 250, 800),
    ("POS 4512XXXXXXXX8891 CAFE COFFEE DAY   PATIALA", 90, 400),
    ("UPI/DR/{ref}/BLINKIT/HDFC/blinkit@ybl/Groceries", 200, 1400),
    ("UPI/DR/{ref}/ZEPTO MARKETPLACE/SBI/zepto@apl/Order", 150, 1100),
    ("POS 4512XXXXXXXX8891 DMART PATIALA", 600, 3500),
    ("UPI/DR/{ref}/MOTHER DAIRY/PNB/dairy@ibl/Milk", 60, 300),
    ("UPI/DR/{ref}/UBER INDIA/HDFC/uber@icici/Ride", 90, 650),
    ("UPI/DR/{ref}/OLA CABS/AXIS/ola@ybl/Trip", 80, 600),
    ("IRCTC RAIL TICKET BOOKING REF {ref}", 350, 2200),
    ("POS 4512XXXXXXXX8891 HPCL PETROL PUMP RAJPURA", 500, 3000),
    ("UPI/DR/{ref}/AMAZON PAY INDIA/HDFC/amazon@apl/Order", 300, 6000),
    ("UPI/DR/{ref}/FLIPKART INTERNET/AXIS/flipkart@ybl/Shopping", 400, 7000),
    ("POS 4512XXXXXXXX8891 MYNTRA DESIGNS BENGALURU", 700, 4500),
    ("UPI/DR/{ref}/JIO RECHARGE/RELIANCE/jio@ybl/Prepaid", 199, 999),
    ("NEFT-AIRTEL BROADBAND BILL-{ref}", 499, 1500),
    ("UPI/DR/{ref}/PSPCL ELECTRICITY/PNB/pspcl@sbi/Bill", 800, 4000),
    ("LIC INSURANCE PREMIUM AUTO DEBIT {ref}", 1200, 4200),
    ("UPI/DR/{ref}/NETFLIX INDIA/HDFC/netflix@ybl/Subscription", 199, 799),
    ("UPI/DR/{ref}/SPOTIFY INDIA/AXIS/spotify@apl/Music", 119, 199),
    ("POS 4512XXXXXXXX8891 PVR CINEMAS CHANDIGARH", 300, 1200),
    ("UPI/DR/{ref}/APOLLO PHARMACY/ICICI/apollo@ybl/Medicines", 120, 1800),
    ("UPI/DR/{ref}/PHARMEASY/HDFC/pharmeasy@apl/Order", 200, 1600),
    ("NEFT-CULT FITNESS GYM MEMBERSHIP-{ref}", 999, 2500),
    ("UPI/DR/{ref}/UDEMY ONLINE/HDFC/udemy@ybl/Course", 449, 3499),
    ("NEFT-IKGPTU COLLEGE FEE-{ref}", 8000, 25000),
    ("UPI/DR/{ref}/HOUSE RENT MARCH/SBI/landlord@oksbi/Rent", 6000, 12000),
    ("ATM CASH WDL 4512XXXXXXXX8891 PATIALA", 500, 5000),
    ("UPI/DR/{ref}/PAYTM QR/HDFC/merchant@paytm/Payment", 50, 900),
    ("UPI/DR/{ref}/LOCAL KIRANA STORE/PNB/kirana@ybl/Pay", 100, 800),
    ("NEFT-CRED CLUB RENT PAYMENT-{ref}", 3000, 9000),
]

CREDITS = [
    ("NEFT-TECHCADD SOLUTIONS SALARY-{ref}", 18000, 22000),
    ("UPI/CR/{ref}/REFUND AMAZON/HDFC/amazon@apl/Return", 300, 2500),
    ("INT.CR SAVINGS INTEREST PAID {ref}", 40, 300),
]


def build_rows():
    rows = []
    start = date.today().replace(day=1) - timedelta(days=330)

    for month_offset in range(11):
        month_start = start + timedelta(days=30 * month_offset)

        # one salary credit per month
        template, low, high = CREDITS[0]
        rows.append(
            (
                month_start + timedelta(days=1),
                template.format(ref=random.randint(10**11, 10**12 - 1)),
                None,
                random.randint(low, high),
            )
        )

        # occasional other credits
        if random.random() < 0.4:
            template, low, high = random.choice(CREDITS[1:])
            rows.append(
                (
                    month_start + timedelta(days=random.randint(2, 27)),
                    template.format(ref=random.randint(10**11, 10**12 - 1)),
                    None,
                    random.randint(low, high),
                )
            )

        # ~17 debits per month
        for _ in range(17):
            template, low, high = random.choice(MERCHANTS)
            amount = random.randint(low, high)
            rows.append(
                (
                    month_start + timedelta(days=random.randint(0, 28)),
                    template.format(ref=random.randint(10**11, 10**12 - 1)),
                    amount,
                    None,
                )
            )

    # one deliberate outlier so anomaly detection has something to find
    rows.append(
        (
            date.today() - timedelta(days=6),
            "UPI/DR/998877665544/SWIGGY/HDFC/swiggy@icici/Party Order",
            9400,
            None,
        )
    )

    rows.sort(key=lambda r: r[0])

    # duplicate two rows exactly (tests dedupe)
    rows.insert(40, rows[38])
    rows.insert(90, rows[87])
    return rows


def write_csv(path):
    rows = build_rows()
    os.makedirs(os.path.dirname(path), exist_ok=True)

    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)

        # junk header block, exactly like a real bank export
        writer.writerow(["Statement of Account"])
        writer.writerow([])
        writer.writerow(["Account Name:", "MR ACCOUNT HOLDER"])
        writer.writerow(["Account Number:", "XXXXXXXX8891"])
        writer.writerow(["Statement Period:", "01/09/2025 to 31/07/2026"])
        writer.writerow([])

        # the real header
        writer.writerow(
            ["Txn Date", "Value Date", "Narration", "Chq/Ref No",
             "Withdrawal Amt.", "Deposit Amt.", "Closing Balance"]
        )

        balance = 45000
        for txn_date, narration, debit, credit in rows:
            balance += (credit or 0) - (debit or 0)
            writer.writerow(
                [
                    txn_date.strftime("%d/%m/%Y"),
                    txn_date.strftime("%d/%m/%Y"),
                    narration,
                    str(random.randint(10**11, 10**12 - 1)),
                    f"{debit:,.2f}" if debit else "",
                    f"{credit:,.2f}" if credit else "",
                    f"{balance:,.2f}",
                ]
            )

        # one malformed row and a footer, both must be skipped
        writer.writerow(["--", "GARBAGE ROW", "", "", "abc", "", ""])
        writer.writerow([])
        writer.writerow(["", "", "Closing Balance", "", "", "", f"{balance:,.2f}"])
        writer.writerow(["*** End of Statement ***"])

    return len(rows)


if __name__ == "__main__":
    target = os.path.join(os.path.dirname(__file__), "..", "data", "sample_statement.csv")
    count = write_csv(os.path.abspath(target))
    print(f"wrote {count} transaction rows to {os.path.abspath(target)}")
