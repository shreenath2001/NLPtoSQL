from main import is_valid_custom_schema_script

print("1:", is_valid_custom_schema_script("CREATE TABLE a (id int);"))
print("2:", is_valid_custom_schema_script("create table a (id int);"))
print("3:", is_valid_custom_schema_script("   CREATE TABLE a (id int);"))
print("4:", is_valid_custom_schema_script("-- comment\nCREATE TABLE a (id int);"))
