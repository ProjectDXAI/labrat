# Dead Ends

- **Raw bag-of-words without TF-IDF**: Consistently worse than TF-IDF on short text
- **Very high max_features (>100K) on 8.5K training set**: Overfits, no generalization
- **Deep neural models on CPU with 8.5K samples**: Too slow and overfit on small data
- **Character-only ngrams without word features**: Loses semantic signal on short reviews
