"""Internal, evidence-based review of historical scheduled service days."""
import argparse,json
from pathlib import Path
import engine,audit

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db',default='data/observatorio.sqlite3')
    sub=parser.add_subparsers(dest='action',required=True)
    r=sub.add_parser('review');r.add_argument('--operator',required=True,choices=list(engine.OPERATORS))
    r.add_argument('--from-date',required=True);r.add_argument('--to-date',required=True)
    r.add_argument('--reviewer',required=True);r.add_argument('--evidence',required=True)
    r.add_argument('--reject',action='store_true')
    sub.add_parser('readiness')
    args=parser.parse_args()
    con=engine.connect(args.db)
    try:
        if args.action=='review':
            out=audit.review_period(con,args.operator,args.from_date,args.to_date,args.reviewer,
                                    args.evidence,'rejected' if args.reject else 'verified')
        else:
            out=audit.readiness(con)
    finally:con.close()
    print(json.dumps(out,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
