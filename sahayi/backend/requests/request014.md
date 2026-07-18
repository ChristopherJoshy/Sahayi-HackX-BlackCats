# Request 014: Fallback to Demo Patient on Unregistered Caller

## Problem
In development and testing environments, if a user dials the Twilio number from an unregistered phone number, the system returns a Malayalam error message and hangs up, which blocks demo usage and testing.

## Solution
Modify the Twilio Voice Handler incoming call webhook logic to:
1. Try to find the patient by caller ID.
2. If not found, look up all patients in the database and fall back to the first available patient profile.
3. Log a warning about the fallback.
4. If no patients exist in the database, retain the original "unregistered caller" Malayalam error response.
