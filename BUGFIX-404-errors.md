# Bug Fix: 404 Errors on Email Reprocessing

## Problem

When running email categorization multiple times, the app was encountering 404 errors when trying to move emails that had already been processed. This happened because:

1. **Root Cause**: When fetching emails from a folder, the orchestrator includes all subfolders (including category folders where emails were already moved)
2. **Filter Not Working**: The `skip_categorized` filter checks if emails have a `categories` array, but moving emails to folders doesn't add category tags
3. **Result**: Already-moved emails were selected again, causing 404 errors when the app tried to move them

## Solution

Added automatic category tagging when moving emails:

### Changes Made

1. **`email_client.py`**:
   - Added `add_category()` method to tag emails with a category
   - Updated `move_email()` to accept optional `category` parameter
   - After successfully moving an email, the app now adds a "Categorized" tag
   - Both primary and fallback move paths add the category tag

2. **`orchestrator.py`**:
   - Updated `process_email()` to pass `category="Categorized"` when moving emails
   - This ensures all moved emails are tagged and won't be reprocessed

3. **`tests/test_email_client_category.py`**:
   - Added comprehensive tests for category tagging functionality
   - Tests cover success/failure cases and both move paths

## How It Works

**Before:**
```
1. Fetch emails from Inbox + subfolders
2. Filter: skip emails with categories (but moved emails have no categories!)
3. Try to move already-moved emails → 404 error
```

**After:**
```
1. Fetch emails from Inbox + subfolders
2. Filter: skip emails with categories
3. Move email to category folder
4. Add "Categorized" tag to email
5. Next run: email is skipped because it has a category tag ✓
```

## Benefits

- **No more 404 errors** on reprocessing
- **Proper deduplication** - emails are only processed once
- **Visible in Outlook** - emails show "Categorized" tag in the UI
- **Backward compatible** - optional parameter, doesn't break existing code

## Testing

Run the new tests:
```bash
pytest tests/test_email_client_category.py -v
```

Test in production:
1. Run categorization on your inbox
2. Run categorization again
3. No 404 errors should appear
4. Check Outlook - moved emails should have "Categorized" tag
