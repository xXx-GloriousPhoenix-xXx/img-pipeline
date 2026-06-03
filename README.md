### main

call:

```
python main.py --from n --to m --output file
python main.py -f n -t m -o file
```

result: ./media/batches/batch-{n}-{m}.txt

### check_limits

call: `python check_limits.py`
result: checks limits of models

### merge

call: `python merge.py`
result: merges batch.txt files into merged.txt

### detect

call: 

```
python detect.py
python detect.py --file file
```

result: prints which questions are absent and unanswered in gived file or merged.txt by default

### restore

call: `python restore.py`
result: inserts questions from `./result/restore/absent.txt` into copied merged.txt (restore.txt)
