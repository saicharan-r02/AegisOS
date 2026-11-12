def binary_search(arr, target):
    low = 0
    high = len(arr)  # BUG: should be len(arr) - 1
    while low <= high:
        mid = (low + high) // 2
        if mid >= len(arr): break
        if arr[mid] == target:
            return mid
        elif arr[mid] < target:
            low = mid + 1
        else:
            high = mid - 1
    return -1
