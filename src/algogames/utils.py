def trysend(f):
    try:
        f()
    except:
        print("Could not submit transaction.")
