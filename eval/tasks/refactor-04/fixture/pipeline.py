def process_numbers(nums):
    for n in nums:
        if n % 2 == 0:
            yield n * 2
