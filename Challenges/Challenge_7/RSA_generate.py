from Crypto.Util.number import getPrime

flag = "HWM{You_Decrypted_It!}"

# Convert the flag to an integer using hex encoding
m = int(flag.encode().hex(), 16)

e = 3

# Generate an RSA modulus
p = getPrime(1024)
q = getPrime(1024)
n = p * q

# Ensure the low-exponent attack works
assert m**3 < n

# Encrypt
c = pow(m, e, n)

print(f"n = {n}")
print(f"e = {e}")
print(f"c = {c}")