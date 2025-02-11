from tableau_api_lib import TableauServerConnection
from tableau_api_lib.utils import querying, flatten_dict_column, flatten_dict_list_column
from tableau_api_lib.utils.querying import get_users_dataframe
import pandas as pd
import sys
from datetime import datetime
import subprocess
import os

# Check and Delete Old Validation file print("Checking the OLD Validation Report Exists ? and Delete , if it does ")

if os.path.exists("/home/drm24/tab-auto/tableau-auto-alloc.log"):
    os.remove("/home/drm24/tab-auto/tableau-auto-alloc.log")
else:
    print("No Old Validation Report Found...")
    
old_stdout = sys.stdout
log_file = open("tableau-auto-alloc.log", "w")
sys.stdout = log_file

# Tableau Server Connection Details

config = { 'tablea_accptnce':
               {'server': 'https://Tableau-server-URL',
                 'api_version': '3.21',
                 'personal_access_token_name': 'mypat1',
                 'personal_access_token_secret': 'XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX',
                 'site_name': 'Tableau Default',
                 'site_url': ''}}

# Create a connection object
conn = TableauServerConnection(config, env='tablea_accptnce',ssl_verify=True)

# Signing in to the Tableau Server
conn.sign_in()

# All Sites User Dataframe to find if a user has creator site role
allsites_df = querying.get_sites_dataframe(conn)
server_users_df = pd.DataFrame()
switch_site_response = []
for index, row in allsites_df.iterrows():
    switch_site_response.append(conn.switch_site(content_url=row["contentUrl"]))
    allusers_df = querying.get_users_dataframe(conn)
    allusers_df['site_name'] = row['name']
    if server_users_df.empty:
        server_users_df = allusers_df
    else:
        server_users_df = pd.concat([server_users_df, allusers_df])

# Converting the Requests file from CSV into a LIST
with open('newritm.csv') as f1:
    ritms = f1.read().splitlines()
#print(f"Request received :- {ritms}")

# Now Loop through the List to process the requests one by one ...
for ritm in ritms:
    myrow = ritm.split(',')
    Rqsno = myrow[0]
    lanid = myrow[1]
    currsite = myrow[2]
    currlic = myrow[3]
    reqsite = myrow[4]
    reqlic = myrow[5]
    reqperm = myrow[6]
    reqdash = myrow[7]
    bulkreq = myrow[8]
    print("------------------------------------------------------------------------")
    print(f"Request No. is :- {Rqsno}")
    print("------------------------------------------------------------------------")
    print(f"Lan ID is :- {lanid}")
    print(f"Requested Site by {lanid} is :- {reqsite}")
    print(f"Requested Site Role by {lanid} is :- {reqlic}")
    # Checking Bulk Request OR NOT ?
    if bulkreq == 'Y':
        print("This is a bulk request , Calling the bulk_access Module")
    # Scan the Input file and Switch site before processing the request
    conn.switch_site(content_url=reqsite)
    site_df = querying.get_users_dataframe(conn)
    site_sub_df = site_df[['name', 'id']]
    site_userid = site_sub_df.loc[site_sub_df['name'] == lanid, ['id']]
    siteuserid = site_userid['id']
    siteuserlst = siteuserid.values.tolist()
    if site_userid.empty:
        print(f"{lanid} does not exist in the {reqsite}, Please add the user to the site ")
        # Checking if the request is for a Creator License
        if reqlic == 'Creator':
            siterole_usr = server_users_df[['name', 'siteRole']]
            usr_max_siterole = siterole_usr.loc[siterole_usr['name'] == lanid, ['siteRole']]
            if usr_max_siterole['siteRole'].eq('Creator').any() and reqlic == 'Creator':
                print(f"{lanid} already has a creator license ,assigning creator/viewer license on the requested site")
                Add_User2Site = conn.add_user_to_site(user_name=lanid, site_role=reqlic)
                if Add_User2Site.status_code == 201:
                    data = Add_User2Site.json()
                    print(f"Sucessfully Added user {lanid} to Tableau Server :- {data}")
                    # Fetching the UserID of the Newly added USer
                    site_df1 = querying.get_users_dataframe(conn)
                    site_sub_df1 = site_df1[['name', 'id']]
                    site_userid1 = site_sub_df1.loc[site_sub_df1['name'] == lanid, ['id']]
                    siteuserid1 = site_userid1['id']
                    siteuserlst1 = siteuserid1.values.tolist()
                    siteuserlst1_uid = siteuserlst1[0]
                else:
                    data = Add_User2Site.json()
                    print(f"Failed to Add user {lanid} to Tableau Server with error code :- {Add_User2Site.status_code}- {data}")
                    # Permission Assignment Code Starts Here :-
                    if reqdash != 'None' and reqperm != 'None':
                        print(f"{lanid} has requested '{reqperm}' access on '{reqdash}' dashboard")
                        project_permissions_df = pd.DataFrame()
                        projects_df = querying.get_projects_dataframe(conn)[["name", "id", "contentPermissions"]]
                        projects_df.rename(columns={"id": "project_id", "name": "project_name"}, inplace=True)
                        # Fetching Users Permissions
                        all_group_users_df = pd.DataFrame()
                        for index, group in groups_df.iterrows():
                            group_users_df = querying.get_group_users_dataframe(conn=conn, group_id=group.id)
                            group_users_df["group_id"] = group["id"]
                            group_users_df["group_name"] = group["name"]
                            group_users_df["domain"] = group["domain"]
                            all_group_users_df = pd.concat([all_group_users_df, group_users_df])

                        # Fetching Group permissions
                        for _, project in projects_df.iterrows():
                            response = conn.query_project_permissions(project_id=project.project_id)
                            try:
                                permissions_df = pd.DataFrame(response.json()["permissions"]["granteeCapabilities"])
                            except KeyError:
                                print(f"skipping project '{project.project_name}'because no permissions rules are defined for it...")
                                continue
                            if "group" not in permissions_df.columns:
                                continue
                            permissions_df = permissions_df[permissions_df["group"].notnull()]
                            permissions_df = flatten_dict_column(df=permissions_df, keys=["id"], col_name="group")
                            permissions_df = flatten_dict_list_column(df=permissions_df, col_name="capabilities")
                            permissions_df = flatten_dict_column(df=permissions_df, keys=["name", "mode"],col_name="capability")
                            permissions_df["project_name"] = project.project_name
                            permissions_df["project_id"] = project.project_id
                            permissions_df["join_col"] = 1

                            project_permissions_df = pd.concat(
                                [project_permissions_df, permissions_df.merge(all_group_users_df, on=["group_id"])]
                            )
                            project_perm_sub_df = project_permissions_df[
                                ["project_id", "project_name", "group_id", "group_name", "capability_name"]].copy()
                            project_perm_uniq_df = project_perm_sub_df.drop_duplicates()
                            project_perm_uniq_df.to_csv("project_permissions.csv", sep=",", header=True, index=False)
                            req_grp_dashbrd_df = project_perm_uniq_df.loc[project_perm_uniq_df['project_name'] == reqdash, ['group_id', 'group_name','capability_name']]
                            print(f"List of groups/users that has access on the '{reqdash}' dashboard are :- ")
                            print(req_grp_dashbrd_df)
                            req_perm_grp_df = req_grp_dashbrd_df.loc[req_grp_dashbrd_df['capability_name'] == reqperm, ['group_name', 'group_id']]
                            print(f"The Group that controls the requested '{reqperm}' permission on '{reqdash}' is/are :- ")
                            print(req_perm_grp_df)
                            req_perm_grp_list = req_perm_grp_df.values.tolist()
                            req_perm_grp_list_gname = req_perm_grp_list[0][0]
                            req_perm_grp_list_gid = req_perm_grp_list[0][1]
                            print(f"The Group ID of Group '{req_perm_grp_list_gname}' is '{req_perm_grp_list_gid}' And the UserID of user '{lanid}' is '{siteuserlst1_uid}'")
                            print(f"Adding user '{lanid}' to the Group '{req_perm_grp_list_gname}'...")
                            Add_User2Grp = conn.add_user_to_group(group_id=req_perm_grp_list_gid,user_id=siteuserlst1_uid)
                            if Add_User2Grp.status_code == 200:
                                data3 = Add_User2Grp.json()
                                print(f"Successfully Added User '{lanid}' to '{req_perm_grp_list_gname}' group")
                            else:
                                data3 = Add_User2Grp.json()
                                print(
                                    f"Failed to Add user '{lanid}' to '{req_perm_grp_list_gid}' group with status code {Add_User2Grp.status_code} :- {data3}")
                        else:
                            print(f"Invalid Request :- {lanid} does not have a creator license on any site , Cannot assign a creator license on the requested site {reqsite}")
                    else:
                        print(f"{lanid} has requested {reqlic}  role on {reqsite} site, Please proceed with new site role assignment")
                        Add_User2Site = conn.add_user_to_site(user_name=lanid, site_role=reqlic)
                        if Add_User2Site.status_code == 201:
                            data = Add_User2Site.json()
                            print(f"Sucessfully Added user {lanid} to Tableau Server :- {data}")
                        else:
                            data = Add_User2Site.json()
                            print(f"Failed to Add user {lanid} to Tableau Server with error code :-  {Add_User2Site.status_code} - {data}")
    else:
        myuserid = siteuserlst[0]
        # code if user already exist on a site and needs creator license
        if reqlic == 'Creator':
            siterole_usr4 = server_users_df[['name', 'siteRole']]
            usr_max_siterole4 = siterole_usr4.loc[siterole_usr4['name'] == lanid, ['siteRole']]
            if usr_max_siterole4['siteRole'].eq('Creator').any() and reqlic == 'Creator':
                print(f"{lanid} already has a creator license , No issues in assigning creator license on the {reqsite} site")
                updt_usr4 = conn.update_user(
                    user_id=myuserid,
                    new_site_role=reqlic
                )
                data4 = updt_usr4.json()
                if updt_usr4.status_code == 200:
                    print(f"Site Role of {lanid} has been updated to {reqlic}")
                else:
                    print(f"Site role of {lanid} could not be updated :- {data4}")

        print(f"User {lanid} is already a member of the site {reqsite}, Updating the Site Role to {reqlic}")
        updt_usr = conn.update_user(
               user_id=myuserid,
               new_site_role=reqlic
        )
        data = updt_usr.json()
        if updt_usr.status_code == 200:
            print(f"Site Role of {lanid} has been updated to {reqlic}")
        else:
            print(f"Site role of {lanid} could not be updated :- {data}")
        # Permission Assignment Code for Existing Site User Starts Here :-
        if reqdash != 'None' and reqperm != 'None':
            print(f"{lanid} has requested '{reqperm}' access on  '{reqdash}' dashboard")
            project_permissions_df1 = pd.DataFrame()
            projects_df1 = querying.get_projects_dataframe(conn)[["name", "id", "contentPermissions"]]
            projects_df1.rename(columns={"id": "project_id", "name": "project_name"}, inplace=True)

            # Fetching Users Permissions
            all_group_users_df1 = pd.DataFrame()
            groups_df1 = querying.get_groups_dataframe(conn)
            for index, group in groups_df1.iterrows():
                # print(f"joining users from group '{group.id}'")
                group_users_df1 = querying.get_group_users_dataframe(conn=conn, group_id=group.id)
                group_users_df1["group_id"] = group["id"]
                group_users_df1["group_name"] = group["name"]
                group_users_df1["domain"] = group["domain"]
                all_group_users_df1 = pd.concat([all_group_users_df1, group_users_df1])

            # Fetching Group permissions
            for _, project in projects_df1.iterrows():
                # print(f"fetching group permissions for project '{project.project_name}...'")
                response1 = conn.query_project_permissions(project_id=project.project_id)
                try:
                    permissions_df1 = pd.DataFrame(response1.json()["permissions"]["granteeCapabilities"])
                except KeyError:
                    print(
                        f"skipping project '{project.project_name}' because no permissions rules are defined for it...")
                    continue
                if "group" not in permissions_df1.columns:
                    continue
                permissions_df1 = permissions_df1[permissions_df1["group"].notnull()]
                permissions_df1 = flatten_dict_column(df=permissions_df1, keys=["id"], col_name="group")
                permissions_df1 = flatten_dict_list_column(df=permissions_df1, col_name="capabilities")
                permissions_df1 = flatten_dict_column(df=permissions_df1, keys=["name", "mode"], col_name="capability")
                permissions_df1["project_name"] = project.project_name
                permissions_df1["project_id"] = project.project_id
                permissions_df1["join_col"] = 1

                project_permissions_df1 = pd.concat(
                    [project_permissions_df1, permissions_df1.merge(all_group_users_df1, on=["group_id"])]
                )
            project_perm_sub_df1 = project_permissions_df1[
                ["project_id", "project_name", "group_id", "group_name", "capability_name"]].copy()
            project_perm_uniq_df1 = project_perm_sub_df1.drop_duplicates()
            project_perm_uniq_df1.to_csv("project_permissions1.csv", sep=",", header=True, index=False)
            req_grp_dashbrd_df1 = project_perm_uniq_df1.loc[
                project_perm_uniq_df1['project_name'] == reqdash, ['group_name', 'capability_name']]
            print(f"List of groups/users that has access on the '{reqdash}' dashboard are :- ")
            print(req_grp_dashbrd_df1)
            req_perm_grp_df1 = req_grp_dashbrd_df1.loc[
                req_grp_dashbrd_df1['capability_name'] == reqperm, ['group_name']]
            print(f"The Group that controls the requested '{reqperm}' permission on '{reqdash}' is/are :- ")
            print(req_perm_grp_df1)
            req_perm_grp_list1 = req_perm_grp_df1.values.tolist()
            print(req_perm_grp_list1)
            req_perm_grp_list_gname1 = req_perm_grp_list1[0][0]
            groups_df3 = querying.get_groups_dataframe(conn)
            group_id_df3 = groups_df3.loc[groups_df3['name'] == req_perm_grp_list_gname1, ['id']]
            group_id_dflist = group_id_df3.values.tolist()
            site_df3 = querying.get_users_dataframe(conn)
            site_sub_df3 = site_df3[['name', 'id']]
            site_userid3 = site_sub_df3.loc[site_sub_df3['name'] == lanid, ['id']]
            siteuserid3 = site_userid3['id']
            siteuserlst3 = siteuserid3.values.tolist()
            siteuserlst3_uid = siteuserlst3[0]
            group_id3 = group_id_dflist[0][0]
            print(
                f"The Group ID of Group '{req_perm_grp_list_gname1}' is '{group_id3}' And the UserID of user '{lanid}' is '{siteuserlst3_uid}'")
            print(f"Adding user '{lanid}' to the Group '{req_perm_grp_list_gname1}'...")
            Add_User2Grp = conn.add_user_to_group(group_id=group_id3, user_id=siteuserlst3_uid)
            if Add_User2Grp.status_code == 200:
                data3 = Add_User2Grp.json()
                print(f"Successfully Added User '{lanid}' to '{req_perm_grp_list_gname1}' group")
            else:
                data3 = Add_User2Grp.json()
                print(
                    f"Failed to Add user '{lanid}' to '{req_perm_grp_list_gname1}' group with status code {Add_User2Grp.status_code} :- {data3}")
        else:
            print(f"Invalid Request :- Requested Dashboard and Requested Permission Value Cannot be 'None'")
        print("")

sys.stdout = old_stdout
log_file.close()
print("Calling the Send Report Script...")
subprocess.call("/home/drm24/tab-auto/send-validation-rpt.sh")
print ("Report sent...")
