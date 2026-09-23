import os
import time
import secrets
import uuid

def generate_uuid7() -> uuid.UUID:
    # 1. Get current timestamp in milliseconds (48 bits)
    # 0xffffffffffff is the mask for 48 bits
    timestamp_ms = int(time.time() * 1000) & 0xFFFFFFFFFFFF
    
    # 2. Generate random bits
    # We need 10 bytes (80 bits) of randomness to fill the rest
    random_bytes = secrets.token_bytes(10)
    
    # 3. Construct the 128-bit integer
    # Layout: [Timestamp 48] [Ver 4] [Rand 12] [Var 2] [Rand 62]
    
    # Version 7 is 0x7
    ver = 0x7
    # Variant is 0x2 (binary 10xx)
    variant = 0x2
    
    # Extract pieces from random_bytes
    rand_a = int.from_bytes(random_bytes[:2], 'big') & 0x0FFF
    rand_b = int.from_bytes(random_bytes[2:], 'big') & 0x3FFFFFFFFFFFFFFF
    
    # Shift and OR everything together
    uuid_int = (timestamp_ms << 80) | (ver << 76) | (rand_a << 64) | (variant << 62) | rand_b

    return uuid.UUID(int=uuid_int)