"""
LSTM model for sequence-based price prediction.
"""
import numpy as np


def create_sequences(X, seq_length=20):
    """Create sequences from feature matrix for LSTM input."""
    sequences = []
    targets = []
    for i in range(len(X) - seq_length):
        sequences.append(X[i:i+seq_length])
        targets.append(X[i+seq_length, -1])  # last feature as target
    return np.array(sequences), np.array(targets)


def create_lstm_model(seq_length, n_features, dropout=0.2):
    """Create and return an LSTM model (requires TensorFlow)."""
    try:
        from tensorflow import keras
        from tensorflow.keras import layers
        
        model = keras.Sequential([
            layers.LSTM(64, activation='relu', input_shape=(seq_length, n_features), return_sequences=True),
            layers.Dropout(dropout),
            layers.LSTM(32, activation='relu'),
            layers.Dropout(dropout),
            layers.Dense(16, activation='relu'),
            layers.Dense(1, activation='sigmoid')
        ])
        model.compile(optimizer='adam', loss='binary_crossentropy', metrics=['accuracy'])
        return model
    except ImportError:
        return None


def train_lstm(X, y, seq_length=20, epochs=10, batch_size=32):
    """Train LSTM on sequences."""
    model = create_lstm_model(seq_length, X.shape[1])
    if model is None:
        return None
    
    X_seq, y_seq = create_sequences(X, seq_length)
    if len(X_seq) == 0:
        return None
    
    model.fit(X_seq, y_seq, epochs=epochs, batch_size=batch_size, verbose=0)
    return model
